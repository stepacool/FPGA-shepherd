from __future__ import annotations

from pathlib import Path

from shepherd.adapters import select
from shepherd.adapters.verilog import VerilogAdapter, scan_sv_subset
from shepherd.config import ProjectConfig


def _cfg(root: Path) -> ProjectConfig:
    return ProjectConfig(
        root=root,
        board="tangnano9k",
        top="top",
        sources=["rtl/top.sv"],
    )


def test_verilog_passthrough(tmp_path: Path):
    src = tmp_path / "rtl" / "top.sv"
    src.parent.mkdir()
    src.write_text("module top; endmodule\n")
    adapter = VerilogAdapter()
    cfg = _cfg(tmp_path)
    assert adapter.detect(cfg, [src])
    assert adapter.emit(cfg, [src], tmp_path / "out") == [src]
    assert select(cfg, [src]).name == "verilog"


def test_sv_subset_rejects_interface(tmp_path: Path):
    path = tmp_path / "bus.sv"
    path.write_text("interface bus;\n  logic clk;\nendinterface\n")
    msgs = scan_sv_subset([path])
    assert msgs
    assert "interface" in msgs[0]
    assert "bus.sv:1" in msgs[0] or str(path) in msgs[0]
