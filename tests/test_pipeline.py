from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shepherd import cli, pipeline
from shepherd.backend.base import Staging, StepResult
from shepherd.context import Context
from shepherd.events.db import EventStore
from shepherd.output import Output

OK_SCRIPT = [("stage", "synth"), ("stage", "pnr"), ("stage", "pack")]
PNR_FAIL_SCRIPT = [
    ("stage", "synth"),
    ("stage", "pnr"),
    ("line", "ERROR: Unconstrained IO:led_OBUF_O"),
]


class FakeBackend:
    """Replays a scripted toolchain run through the sink, like a real backend would."""

    name = "fake"

    def __init__(self, build_script=OK_SCRIPT, build_code=0, upload_code=0, dry_run=False):
        self.dry_run = dry_run
        self.build_script = build_script
        self.build_code = build_code
        self.upload_code = upload_code
        self.calls = []

    def resolve_board(self, name):
        return name

    def prepare(self, cfg, sources, constraints, *, flash=False):
        stage = Staging(dir=cfg.root / ".shepherd" / "build", keep={"_build"})
        for i, src in enumerate(sources):
            stage.links[f"src/{i:03d}_{src.name}"] = src
        stage.files["project.ini"] = f"flash={flash}\n"
        return stage

    def _replay(self, step, script, code, log_path, sink):
        self.calls.append(step)
        sink.command(["fake", step])
        if self.dry_run:
            return StepResult(step, True, 0, None, dry_run=True)
        with open(log_path, "a") as log:
            for kind, value in script:
                log.write(value + "\n")
                getattr(sink, kind)(value)
        return StepResult(step, code == 0, code, log_path, commands=[["fake", step]])

    def build(self, staging, log_path, sink, *, verbose=False):
        result = self._replay("build", self.build_script, self.build_code, log_path, sink)
        if result.ok and not result.dry_run:
            bitstream = staging.dir / "_build" / "hardware.fs"
            bitstream.parent.mkdir(parents=True, exist_ok=True)
            bitstream.write_text("bits")
            result.artifacts["bitstream"] = bitstream
        return result

    def upload(self, staging, log_path, sink):
        return self._replay("upload", [("line", "Done")], self.upload_code, log_path, sink)

    def passthrough(self, args, cwd):
        return 0


def run(project: Path, command="build", backend=None, **flags):
    ctx = Context(project=project, **flags)
    backend = backend or FakeBackend()
    return pipeline.Pipeline(ctx, Output(ctx), backend).run(command), backend


def kinds(project: Path, run_id: str) -> list[tuple[str, str]]:
    store = EventStore.open(project)
    return [(e["kind"], e["step"]) for e in store.events(run_id)]


def test_build_pass_writes_run_events_logs_and_artifact(project: Path):
    result, _ = run(project)
    assert result.verdict == "pass"
    assert [s.name for s in result.steps] == ["synth", "pnr", "pack"]
    assert kinds(project, result.run_id) == [
        ("step_start", "adapter"),
        ("step_end", "adapter"),
        ("step_start", "synth"),
        ("step_end", "synth"),
        ("step_start", "pnr"),
        ("step_end", "pnr"),
        ("step_start", "pack"),
        ("step_end", "pack"),
        ("artifact", "pack"),
        ("verdict", "verify"),
    ]
    store = EventStore.open(project)
    row = store.latest_run()
    assert (row["command"], row["verdict"]) == ("build", "pass")
    run_dir = project / ".shepherd" / "runs" / result.run_id
    assert (run_dir / "build.log").exists()
    assert "src/000_blinky.v" in (run_dir / "adapter.log").read_text()
    assert not (run_dir / "pid").exists()
    assert not (project / ".shepherd" / "lock").exists()
    assert (project / ".shepherd" / "build" / "src" / "000_blinky.v").is_symlink()


def test_build_fail_stops_and_reports(project: Path, capsys):
    backend = FakeBackend(build_script=PNR_FAIL_SCRIPT, build_code=2)
    result, _ = run(project, backend=backend)
    assert result.verdict == "fail"
    assert [(s.name, s.ok) for s in result.steps] == [("synth", True), ("pnr", False)]
    out = capsys.readouterr().out
    assert "pnr" in out and "FAIL" in out
    assert "error: Unconstrained IO:led_OBUF_O" in out
    assert "build.log" in out
    events = EventStore.open(project).events(result.run_id)
    errors = [e["message"] for e in events if e["kind"] == "log" and e["level"] == "error"]
    assert errors == ["ERROR: Unconstrained IO:led_OBUF_O"]
    assert EventStore.open(project).latest_run()["verdict"] == "fail"


def test_cached_build_marks_stages_up_to_date(project: Path, capsys):
    result, _ = run(project, backend=FakeBackend(build_script=[]))
    assert result.verdict == "pass"
    assert [(s.name, s.cached) for s in result.steps] == [
        ("synth", True),
        ("pnr", True),
        ("pack", True),
    ]
    assert "up to date" in capsys.readouterr().out


def test_upload_runs_build_then_upload(project: Path):
    result, backend = run(project, command="upload")
    assert backend.calls == ["build", "upload"]
    assert result.steps[-1].name == "upload"
    assert result.verdict == "pass"


def test_upload_skipped_when_build_fails(project: Path):
    backend = FakeBackend(build_script=PNR_FAIL_SCRIPT, build_code=2)
    result, _ = run(project, command="upload", backend=backend)
    assert backend.calls == ["build"]
    assert result.verdict == "fail"


def test_dry_run_writes_nothing(project: Path, capsys):
    result, _ = run(project, "upload", backend=FakeBackend(dry_run=True), dry_run=True)
    assert result.dry_run
    assert not (project / ".shepherd").exists()
    out = capsys.readouterr().out
    assert "src/000_blinky.v -> rtl/blinky.v" in out
    assert "backend: fake build" in out and "backend: fake upload" in out


def test_missing_constraints(project: Path):
    from shepherd.errors import ConfigError

    (project / "tangnano9k.cst").unlink()
    with pytest.raises(ConfigError, match="constraints"):
        run(project)


def test_cancel_marks_run_failed_and_releases_lock(project: Path):
    class Cancelling(FakeBackend):
        def build(self, staging, log_path, sink, *, verbose=False):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run(project, backend=Cancelling())
    row = EventStore.open(project).latest_run()
    assert row["verdict"] == "fail"
    assert row["finished_at"] is not None
    assert not (project / ".shepherd" / "lock").exists()


def test_cli_json_is_the_only_stdout(project: Path, monkeypatch):
    monkeypatch.setattr(pipeline, "get_backend", lambda dry_run=False: FakeBackend())
    result = CliRunner().invoke(cli.app, ["--json", "--project", str(project), "build"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["verdict"] == "pass"
    assert data["command"] == "build"
    assert [s["name"] for s in data["steps"]] == ["synth", "pnr", "pack"]
    assert "bitstream" in data["artifacts"]
    assert "verdict" in result.stderr


def test_cli_fail_exit_code(project: Path, monkeypatch):
    backend = FakeBackend(build_script=PNR_FAIL_SCRIPT, build_code=2)
    monkeypatch.setattr(pipeline, "get_backend", lambda dry_run=False: backend)
    result = CliRunner().invoke(cli.app, ["--project", str(project), "build"])
    assert result.exit_code == 1


def test_default_output_has_no_backend_terms(project: Path, monkeypatch):
    monkeypatch.setattr(pipeline, "get_backend", lambda dry_run=False: FakeBackend())
    result = CliRunner().invoke(cli.app, ["--project", str(project), "upload"])
    assert result.exit_code == 0
    assert "fake" not in result.output
    assert "apio" not in result.output.lower()
