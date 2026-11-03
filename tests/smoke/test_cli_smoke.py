"""Optional toolchain smoke tests (skipped when the toolchain is absent)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shepherd import cli

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[2]


def _toolchain_present() -> bool:
    return shutil.which("yosys") is not None or shutil.which("nextpnr-himbaechel") is not None


toolchain = pytest.mark.toolchain


@toolchain
@pytest.mark.skipif(not _toolchain_present(), reason="FPGA toolchain not installed")
def test_blinky_dry_run():
    result = runner.invoke(
        cli.app, ["build", "--dry-run", "--project", str(ROOT / "examples" / "blinky_sv")]
    )
    assert result.exit_code == 0, result.output
    assert "apio" not in result.output.lower() or "backend:" in result.output


def test_help_has_no_backend_leak():
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    assert "apio" not in result.output.lower()
