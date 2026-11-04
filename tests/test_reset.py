from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from shepherd import cli

runner = CliRunner()


def test_reset_fpga(project: Path, monkeypatch):
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "Jtag frequency : requested 6.00MHz\n"
        stderr = ""

    def fake_which(name: str) -> str | None:
        return "/usr/bin/openFPGALoader" if name == "openFPGALoader" else None

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return Result()

    monkeypatch.setattr("shepherd.reset_cmd.shutil.which", fake_which)
    monkeypatch.setattr("shepherd.reset_cmd.subprocess.run", fake_run)

    result = runner.invoke(cli.app, ["--project", str(project), "reset", "--yes"])
    assert result.exit_code == 0, result.output
    assert "SRAM" in result.output or "reset" in result.output.lower()
    assert calls, "openFPGALoader was not invoked"
    assert calls[0][0].endswith("openFPGALoader")
    assert "-b" in calls[0] and "tangnano9k" in calls[0]
    assert "-r" in calls[0]


def test_reset_dry_run_does_not_touch_board(project: Path, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("subprocess must not run on dry-run")

    monkeypatch.setattr(
        "shepherd.reset_cmd.shutil.which",
        lambda name: "/usr/bin/openFPGALoader" if name == "openFPGALoader" else None,
    )
    monkeypatch.setattr("shepherd.reset_cmd.subprocess.run", boom)

    result = runner.invoke(cli.app, ["--project", str(project), "reset", "--dry-run", "--yes"])
    assert result.exit_code == 0, result.output
    assert "dry run" in result.output.lower()


def test_reset_missing_tool(project: Path, monkeypatch):
    monkeypatch.setattr("shepherd.reset_cmd.shutil.which", lambda _name: None)
    result = runner.invoke(cli.app, ["--project", str(project), "reset", "--yes"])
    assert result.exit_code != 0
    assert "programmer" in result.output.lower() or "not found" in result.output.lower()
