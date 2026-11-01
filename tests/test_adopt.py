from __future__ import annotations

from pathlib import Path

from shepherd import adopt


def test_propose_detects_blinky(tmp_path: Path):
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "blinky.sv").write_text(
        "module blinky (input clk, output led); endmodule\n"
    )
    (tmp_path / "tangnano9k.cst").write_text('IO_LOC "clk" 52;\n')
    proposal = adopt.propose(tmp_path)
    assert proposal.created is True
    assert proposal.needs_scaffold is False
    assert proposal.cfg is not None
    assert proposal.cfg.top == "blinky"
    assert proposal.cfg.sources == ["rtl/blinky.sv"]
    assert proposal.cfg.constraints == "tangnano9k.cst"
    assert proposal.cfg.board == "tangnano9k"


def test_propose_keeps_existing_toml(tmp_path: Path):
    (tmp_path / "shepherd.toml").write_text(
        'board = "tangnano9k"\ntop = "other"\nsources = ["a.v"]\n'
    )
    (tmp_path / "a.v").write_text("module other; endmodule\n")
    proposal = adopt.propose(tmp_path)
    assert proposal.created is False
    assert proposal.needs_scaffold is False
    assert proposal.cfg is not None
    assert proposal.cfg.top == "other"


def test_propose_empty_needs_scaffold(tmp_path: Path):
    proposal = adopt.propose(tmp_path)
    assert proposal.needs_scaffold is True
    assert proposal.cfg is None


def test_skips_testbenches(tmp_path: Path):
    (tmp_path / "top.v").write_text("module top; endmodule\n")
    (tmp_path / "top_tb.v").write_text("module top_tb; endmodule\n")
    proposal = adopt.propose(tmp_path)
    assert proposal.cfg is not None
    assert proposal.cfg.sources == ["top.v"]
    assert proposal.cfg.top == "top"
