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


@pytest.mark.parametrize("args", [["doctor"], ["lint"], ["report"], ["ask", "why?"], ["ui"]])
def test_unimplemented_commands_exit_2(args):
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 2
    assert "not implemented yet" in result.output


def test_init_adopts_existing_toml(tmp_path: Path, monkeypatch):
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "blinky.sv").write_text("module blinky; endmodule\n")
    (tmp_path / "shepherd.toml").write_text(
        'board = "tangnano9k"\ntop = "blinky"\nsources = ["rtl/blinky.sv"]\n'
    )

    class FakeBackend:
        def ensure_toolchain(self, sink):
            from shepherd.backend.base import StepResult

            return StepResult("toolchain", True, 0, None)

    monkeypatch.setattr("shepherd.init_cmd.get_backend", lambda dry_run=False: FakeBackend())
    result = runner.invoke(cli.app, ["--project", str(tmp_path), "init"])
    assert result.exit_code == 0, result.output
    assert "found shepherd.toml" in result.output
    assert "packages ready" in result.output


def test_init_writes_toml_for_detected_hdl(tmp_path: Path, monkeypatch):
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "blinky.sv").write_text(
        "module blinky (input clk, output led); endmodule\n"
    )
    (tmp_path / "tangnano9k.cst").write_text('IO_LOC "clk" 52;\n')

    class FakeBackend:
        def ensure_toolchain(self, sink):
            from shepherd.backend.base import StepResult

            return StepResult("toolchain", True, 0, None)

    monkeypatch.setattr("shepherd.init_cmd.get_backend", lambda dry_run=False: FakeBackend())
    result = runner.invoke(cli.app, ["init", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "wrote shepherd.toml" in result.output
    text = (tmp_path / "shepherd.toml").read_text()
    assert 'top = "blinky"' in text
    assert "rtl/blinky.sv" in text
    assert "tangnano9k.cst" in text


def _fake_toolchain(monkeypatch):
    class FakeBackend:
        def ensure_toolchain(self, sink):
            from shepherd.backend.base import StepResult

            return StepResult("toolchain", True, 0, None)

    monkeypatch.setattr("shepherd.init_cmd.get_backend", lambda dry_run=False: FakeBackend())


def test_init_scaffolds_empty_with_yes(tmp_path: Path, monkeypatch):
    _fake_toolchain(monkeypatch)
    result = runner.invoke(cli.app, ["-y", "init", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "created starter files" in result.output
    assert (tmp_path / "rtl" / "top.sv").is_file()
    assert (tmp_path / "tangnano9k.cst").is_file()
    assert (tmp_path / "shepherd.toml").is_file()
    text = (tmp_path / "shepherd.toml").read_text()
    assert 'top = "top"' in text
    assert "rtl/top.sv" in text


def test_init_scaffold_aborts_on_existing_file(tmp_path: Path, monkeypatch):
    _fake_toolchain(monkeypatch)
    # Empty of HDL, but a scaffold target already exists → abort, do not replace.
    (tmp_path / "tangnano9k.cst").write_text('IO_LOC "clk" 52;\n')
    result = runner.invoke(cli.app, ["-y", "init", str(tmp_path)])
    assert result.exit_code == 2, result.output
    assert "refusing to replace" in result.output
    assert "tangnano9k.cst" in result.output
    assert "remove those file" in result.output
    assert not (tmp_path / "shepherd.toml").exists()


def test_init_scaffold_cancelled(tmp_path: Path, monkeypatch):
    _fake_toolchain(monkeypatch)
    result = runner.invoke(cli.app, ["init", str(tmp_path)], input="n\n")
    assert result.exit_code == 2, result.output
    assert "init cancelled" in result.output
    assert not (tmp_path / "shepherd.toml").exists()


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
