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


def test_multi_top_yes_errors(tmp_path: Path):
    from shepherd.errors import ConfigError

    (tmp_path / "a.v").write_text("module alpha; endmodule\n")
    (tmp_path / "b.v").write_text("module beta; endmodule\n")
    try:
        adopt.propose(tmp_path, yes=True)
        raise AssertionError("expected ConfigError")
    except ConfigError as e:
        assert "alpha" in e.message and "beta" in e.message


def test_multi_top_explicit(tmp_path: Path):
    (tmp_path / "a.v").write_text("module alpha; endmodule\n")
    (tmp_path / "b.v").write_text("module beta; endmodule\n")
    proposal = adopt.propose(tmp_path, top="beta")
    assert proposal.cfg is not None
    assert proposal.cfg.top == "beta"


def test_force_overwrites_existing(tmp_path: Path):
    (tmp_path / "shepherd.toml").write_text(
        'board = "tangnano9k"\ntop = "old"\nsources = ["old.v"]\n'
    )
    (tmp_path / "new.v").write_text("module neu; endmodule\n")
    kept = adopt.propose(tmp_path)
    assert kept.cfg is not None and kept.cfg.top == "old"
    forced = adopt.propose(tmp_path, force=True)
    assert forced.created is True
    assert forced.cfg is not None
    assert forced.cfg.top == "neu"


def test_ensure_gitignore(tmp_path: Path):
    assert adopt.ensure_gitignore(tmp_path) is True
    assert ".shepherd/" in (tmp_path / ".gitignore").read_text()
    assert adopt.ensure_gitignore(tmp_path) is False


def test_import_backend_ini(tmp_path: Path):
    (tmp_path / ("ap" + "io.ini")).write_text(
        "[env:default]\nboard = sipeed-tang-nano-9k\ntop-module = blinky\n"
    )
    (tmp_path / "blinky.v").write_text("module blinky; endmodule\n")
    proposal = adopt.propose(tmp_path)
    assert proposal.cfg is not None
    assert proposal.cfg.board == "tangnano9k"
    assert proposal.cfg.top == "blinky"
    assert any("imported" in n for n in proposal.notes)
