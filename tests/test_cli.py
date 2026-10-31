from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shepherd import cli

runner = CliRunner()

COMMANDS = [
    "doctor",
    "init",
    "build",
    "upload",
    "lint",
    "sim",
    "test",
    "report",
    "check",
    "explain",
    "ask",
    "ui",
    "help",
]


@pytest.mark.parametrize("args", [["--help"], ["-h"], ["help"], []])
def test_top_level_help(args):
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 0
    assert "Usage: shepherd" in result.output
    for name in ("build", "upload", "doctor", "init"):
        assert name in result.output


def test_backend_command_hidden_from_help():
    result = runner.invoke(cli.app, ["--help"])
    assert re.search(r"^\W*backend\s", result.output, re.MULTILINE) is None


@pytest.mark.parametrize("command", COMMANDS)
def test_command_help_has_no_backend_leak(command):
    for args in ([command, "--help"], [command, "-h"], ["help", command]):
        result = runner.invoke(cli.app, args)
        assert result.exit_code == 0, (args, result.output)
        assert f"shepherd {command}" in result.output
        assert "apio" not in result.output.lower()


def test_help_unknown_command():
    result = runner.invoke(cli.app, ["help", "nope"])
    assert result.exit_code == 2


def test_version():
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0
    assert result.output.startswith("shepherd ")


@pytest.mark.parametrize(
    "args", [["doctor"], ["init"], ["lint"], ["report"], ["ask", "why?"], ["ui"]]
)
def test_unimplemented_commands_exit_2(args):
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 2
    assert "not implemented yet" in result.output


def test_global_flags_land_on_context(tmp_path: Path, monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "_not_implemented", lambda name: seen.update(ctx=cli._current))
    args = [
        "--no-ai",
        "--no-check",
        "-y",
        "--json",
        "--dry-run",
        "--show-backend",
        "-v",
        "--project",
        str(tmp_path),
        "--run-id",
        "r1",
        "doctor",
    ]
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 0, result.output
    ctx = seen["ctx"]
    assert (ctx.no_ai, ctx.no_check, ctx.yes, ctx.json) == (True, True, True, True)
    assert (ctx.dry_run, ctx.show_backend, ctx.verbose) == (True, True, True)
    assert ctx.project == tmp_path.resolve()
    assert ctx.run_id == "r1"
