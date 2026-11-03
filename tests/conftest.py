from __future__ import annotations

from pathlib import Path

import pytest

BLINKY = """module blinky (input clk, output reg led);
  always @(posedge clk) led <= ~led;
endmodule
"""


@pytest.fixture(autouse=True)
def _plain_cli_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep Typer/Rich help text free of ANSI so string asserts stay stable in CI/TTY."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("CLICOLOR_FORCE", raising=False)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A minimal valid Shepherd project."""
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "blinky.v").write_text(BLINKY)
    (tmp_path / "tangnano9k.cst").write_text('IO_LOC "clk" 52;\nIO_LOC "led" 10;\n')
    (tmp_path / "shepherd.toml").write_text(
        'board = "tangnano9k"\ntop = "blinky"\nsources = ["rtl/blinky.v"]\n'
    )
    return tmp_path
