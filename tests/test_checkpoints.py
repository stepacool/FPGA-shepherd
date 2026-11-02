from __future__ import annotations

from pathlib import Path

import pytest

from shepherd.backend.base import Staging
from shepherd.checks.checkpoints import CheckContext, check
from shepherd.config import ProjectConfig

FIXTURES = Path(__file__).parent / "fixtures" / "apio"


def _cfg(root: Path, top: str = "blinky") -> ProjectConfig:
    return ProjectConfig(
        root=root,
        board="tangnano9k",
        top=top,
        sources=["rtl/blinky.v"],
        constraints="tangnano9k.cst",
        adapters={},
        checks_ai=True,
    )


def test_adapter_pass(tmp_path: Path):
    src = tmp_path / "rtl" / "blinky.v"
    src.parent.mkdir()
    src.write_text("module blinky (input clk, output led); endmodule\n")
    staging = Staging(dir=tmp_path / ".shepherd" / "build")
    staging.links["src/000_blinky.v"] = src
    staging.write()
    result = check(
        "adapter",
        CheckContext(stage="adapter", staging_dir=staging.dir, cfg=_cfg(tmp_path), staging=staging),
    )
    assert result.ok


def test_adapter_missing_top(tmp_path: Path):
    src = tmp_path / "rtl" / "blinky.v"
    src.parent.mkdir()
    src.write_text("module other; endmodule\n")
    staging = Staging(dir=tmp_path / ".shepherd" / "build")
    staging.links["src/000_blinky.v"] = src
    staging.write()
    result = check(
        "adapter",
        CheckContext(stage="adapter", staging_dir=staging.dir, cfg=_cfg(tmp_path), staging=staging),
    )
    assert not result.ok
    assert "top module" in result.message


def test_adapter_broken_symlink(tmp_path: Path):
    staging = Staging(dir=tmp_path / ".shepherd" / "build")
    staging.links["src/000_blinky.v"] = tmp_path / "rtl" / "missing.v"
    staging.write()
    result = check(
        "adapter",
        CheckContext(stage="adapter", staging_dir=staging.dir, cfg=_cfg(tmp_path), staging=staging),
    )
    assert not result.ok


@pytest.mark.parametrize(
    ("stage", "fixture", "ok"),
    [
        ("synth", "build_ok.log", True),
        ("pnr", "build_ok.log", True),
        ("pack", "build_ok.log", True),
        ("pnr", "build_pnr_unconstrained.log", False),
        ("synth", "build_syntax_error.log", False),
    ],
)
def test_build_stage_fixtures(tmp_path: Path, stage: str, fixture: str, ok: bool):
    staging_dir = tmp_path / ".shepherd" / "build"
    cache = staging_dir / "_build" / "default"
    cache.mkdir(parents=True)
    log_text = (FIXTURES / fixture).read_text()
    if fixture == "build_ok.log":
        (cache / "hardware.json").write_text("{}")
        (cache / "hardware.pnr.json").write_text("{}")
        (cache / "hardware.fs").write_text("bits")
    elif fixture == "build_pnr_unconstrained.log":
        (cache / "hardware.json").write_text("{}")
    elif fixture == "build_syntax_error.log":
        pass
    result = check(
        stage,
        CheckContext(
            stage=stage,
            staging_dir=staging_dir,
            cfg=_cfg(tmp_path),
            returncode=0 if ok else 2,
            log_text=log_text,
        ),
    )
    assert result.ok is ok


def test_pack_requires_nonempty_bitstream(tmp_path: Path):
    staging_dir = tmp_path / ".shepherd" / "build"
    cache = staging_dir / "_build" / "default"
    cache.mkdir(parents=True)
    (cache / "hardware.fs").write_text("")
    result = check(
        "pack",
        CheckContext(stage="pack", staging_dir=staging_dir, cfg=_cfg(tmp_path), returncode=0),
    )
    assert not result.ok


def test_upload_pass_and_ftdi_fail(tmp_path: Path):
    staging_dir = tmp_path / ".shepherd" / "build"
    staging_dir.mkdir(parents=True)
    ok = check(
        "upload",
        CheckContext(
            stage="upload",
            staging_dir=staging_dir,
            cfg=_cfg(tmp_path),
            returncode=0,
            log_text="Jtag frequency\nDone\n",
        ),
    )
    assert ok.ok
    bad = check(
        "upload",
        CheckContext(
            stage="upload",
            staging_dir=staging_dir,
            cfg=_cfg(tmp_path),
            returncode=1,
            log_text="Error: unable to open ftdi device: 1\n",
        ),
    )
    assert not bad.ok
    assert bad.findings[0].fix and "doctor" in bad.findings[0].fix
