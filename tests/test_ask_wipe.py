from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from shepherd import cli
from shepherd.config import STATE_DIR
from shepherd.events.db import EventStore
from shepherd.events.logs import RunDir

runner = CliRunner()


def test_ask_wipe_clears_db_and_runs_keeps_build(project: Path):
    store = EventStore.open(project)
    run = store.start_run("build", board="tangnano9k", run_id="old-run")
    RunDir(project, run.id).log_path("build").write_text("noise\n")
    run.finish("pass")
    store.close()

    build_dir = project / STATE_DIR / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "hardware.fs").write_text("fake\n")
    gen_dir = project / STATE_DIR / "gen"
    gen_dir.mkdir(parents=True, exist_ok=True)
    (gen_dir / "out.v").write_text("module x; endmodule\n")

    result = runner.invoke(cli.app, ["--project", str(project), "ask", "wipe", "--yes"])
    assert result.exit_code == 0, result.output
    assert "wiped" in result.output.lower()

    assert not (project / STATE_DIR / "runs" / "old-run").exists()
    assert (build_dir / "hardware.fs").is_file()
    assert (gen_dir / "out.v").is_file()

    store = EventStore.open(project)
    try:
        latest = store.latest_run()
        assert latest is not None
        assert latest["command"] == "wipe"
        assert latest["verdict"] == "pass"
        old = store.conn.execute("SELECT 1 FROM runs WHERE id = ?", ("old-run",)).fetchone()
        assert old is None
    finally:
        store.close()


def test_ask_wipe_nothing_to_wipe(project: Path):
    result = runner.invoke(cli.app, ["--project", str(project), "ask", "wipe", "--yes"])
    assert result.exit_code == 0, result.output
    assert "nothing to wipe" in result.output.lower() or "wiped 0" in result.output.lower()


def test_ask_wipe_dry_run_does_not_delete(project: Path):
    store = EventStore.open(project)
    run = store.start_run("ask", board="tangnano9k", run_id="keep-me")
    run.finish("pass")
    store.close()
    RunDir(project, "keep-me")

    result = runner.invoke(
        cli.app, ["--project", str(project), "ask", "wipe", "--dry-run", "--yes"]
    )
    assert result.exit_code == 0, result.output
    assert (project / STATE_DIR / "shepherd.db").is_file()
    assert (project / STATE_DIR / "runs" / "keep-me").is_dir()
