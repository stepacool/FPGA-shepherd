from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

from shepherd import config
from shepherd.backend.apio import ApioBackend, parse, project, runner
from shepherd.backend.base import NullSink
from shepherd.errors import UnknownBoard

FIXTURES = Path(__file__).parent / "fixtures"
SRC = Path(__file__).parent.parent / "src" / "shepherd"


class RecordingSink:
    def __init__(self):
        self.commands, self.stages, self.lines = [], [], []

    def command(self, argv):
        self.commands.append(argv)

    def stage(self, name):
        self.stages.append(name)

    def line(self, text):
        self.lines.append(text)


def test_board_allowlist():
    assert project.resolve_board("tangnano9k") == "sipeed-tang-nano-9k"
    with pytest.raises(UnknownBoard) as err:
        project.resolve_board("icebreaker")
    assert "tangnano9k" in err.value.hint
    assert "apio" not in err.value.message + err.value.hint


def test_apio_ini_sram_default_and_flash():
    sram = project.apio_ini("sipeed-tang-nano-9k", "blinky", constraints=True, flash=False)
    assert "[env:default]" in sram
    assert "top-module = blinky" in sram
    assert "constraint-file = constraints.cst" in sram
    assert " -f " not in sram and "${BIN_FILE}" in sram
    flash = project.apio_ini("sipeed-tang-nano-9k", "blinky", constraints=False, flash=True)
    assert " -f ${BIN_FILE}" in flash
    assert "constraint-file" not in flash


def _cfg(root: Path, sources: list[str]) -> config.ProjectConfig:
    for name in sources:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("module m; endmodule\n")
    return config.ProjectConfig(root=root, board="tangnano9k", top="m", sources=sources)


def test_staging_preserves_order_and_testbench_names(tmp_path: Path):
    cfg = _cfg(tmp_path, ["rtl/zeta.v", "rtl/alpha.sv", "tb/alpha_tb.sv"])
    cst = tmp_path / "pins.cst"
    cst.write_text("")
    stage = project.build_staging(cfg, config.resolve_sources(cfg), cst)
    names = [n for n in stage.links if n.startswith("src/")]
    assert names == ["src/000_zeta.v", "src/001_alpha.sv", "src/002_alpha_tb.sv"]
    assert sorted(names) == names  # the backend's lexicographic sort keeps our order
    assert stage.links["constraints.cst"] == cst
    assert stage.dir == tmp_path / ".shepherd" / "build"


def test_staging_write_links_and_keeps_cache(tmp_path: Path):
    cfg = _cfg(tmp_path, ["rtl/a.v"])
    stage = project.build_staging(cfg, config.resolve_sources(cfg), None)
    cache = stage.dir / "_build" / "default"
    cache.mkdir(parents=True)
    (cache / "hardware.fs").write_text("bits")
    (stage.dir / "src").mkdir()
    (stage.dir / "src" / "000_stale.v").write_text("")

    stage.write()

    link = stage.dir / "src" / "000_a.v"
    assert link.is_symlink()
    assert not os.path.isabs(os.readlink(link))
    assert link.resolve() == (tmp_path / "rtl" / "a.v").resolve()
    assert not (stage.dir / "src" / "000_stale.v").exists()
    assert (cache / "hardware.fs").read_text() == "bits"
    assert "top-module = m" in (stage.dir / "apio.ini").read_text()


def test_path_map(tmp_path: Path):
    cfg = _cfg(tmp_path, ["rtl/a.v"])
    stage = project.build_staging(cfg, config.resolve_sources(cfg), None)
    assert stage.path_map == {stage.dir / "src/000_a.v": (tmp_path / "rtl/a.v").resolve()}


def test_dry_run_runs_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(runner, "run", lambda *a, **k: pytest.fail("subprocess started"))
    cfg = _cfg(tmp_path, ["a.v"])
    backend = ApioBackend(dry_run=True)
    stage = backend.prepare(cfg, config.resolve_sources(cfg), None)
    sink = RecordingSink()
    result = backend.build(stage, None, sink)
    assert result.ok and result.dry_run
    assert sink.commands[0][-1] == "build"
    assert not stage.dir.exists()


@pytest.mark.parametrize(
    ("fixture", "code", "stages", "ok"),
    [
        ("build_ok.log", 0, ["synth", "pnr", "pack"], True),
        ("build_pnr_unconstrained.log", 2, ["synth", "pnr"], False),
        ("build_syntax_error.log", 2, ["synth"], False),
    ],
)
def test_build_with_fake_apio(tmp_path: Path, monkeypatch, fixture, code, stages, ok):
    """Replays real apio output through the runner using a fake executable."""
    fake = tmp_path / "fake_apio.py"
    fake.write_text(
        "import sys\n"
        f"sys.stdout.write(open({str(FIXTURES / 'apio' / fixture)!r}).read())\n"
        f"sys.exit({code})\n"
    )
    monkeypatch.setattr(runner, "apio_argv", lambda: [sys.executable, str(fake)])
    cfg = _cfg(tmp_path / "proj", ["a.v"])
    backend = ApioBackend()
    stage = backend.prepare(cfg, config.resolve_sources(cfg), None)
    stage.write()
    log = tmp_path / "build.log"
    sink = RecordingSink()

    result = backend.build(stage, log, sink)

    assert result.ok is ok
    assert result.returncode == code
    assert sink.stages == stages
    assert log.read_text() == (FIXTURES / "apio" / fixture).read_text()
    # Backend banners are kept in the log but never forwarded to the user.
    assert not any("Using env" in line or "SUCCESS" in line for line in sink.lines)
    if not ok:
        assert any("ERROR" in line for line in sink.lines)


def test_runner_missing_executable(tmp_path: Path):
    from shepherd.errors import EnvironmentProblem

    with pytest.raises(EnvironmentProblem):
        runner.run([str(tmp_path / "nope")], tmp_path, None, NullSink().line)


def test_stage_detection_and_noise():
    assert parse.detect_stage('yosys -p "synth_gowin -top x"') == "synth"
    assert parse.detect_stage("nextpnr-himbaechel --device GW1NR") == "pnr"
    assert parse.detect_stage("gowin_pack -d GW1N-9C -o x.fs") == "pack"
    assert parse.detect_stage("openFPGALoader -b tangnano9k x.fs") == "upload"
    assert parse.detect_stage("ERROR: Unconstrained IO:led") is None
    assert parse.is_noise("Using env default (sipeed-tang-nano-9k)")
    assert parse.is_noise("=" * 25 + " [SUCCESS] Took 27.82 seconds " + "=" * 25)
    assert not parse.is_noise("ERROR: Unconstrained IO:led_OBUF_O")


def test_backend_name_only_inside_backend_package():
    """Nothing outside backend/apio/ may know the backend exists (factory facade excepted)."""
    allowed = {SRC / "backend" / "__init__.py"}
    offenders = []
    for path in SRC.rglob("*.py"):
        if (SRC / "backend" / "apio") in path.parents or path in allowed:
            continue
        if re.search(r"apio", path.read_text(), re.IGNORECASE):
            offenders.append(str(path.relative_to(SRC)))
    assert offenders == []
