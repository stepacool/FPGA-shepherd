"""Starter files for `shepherd init` on an empty project folder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shepherd.adopt import DEFAULT_BOARD
from shepherd.config import ProjectConfig, dump

# Minimal Tang Nano 9K blinky-shaped skeleton (LEDs active low).
TOP_SV = """\
// Starter top for Tang Nano 9K. Edit me.
module top #(
    parameter int CLK_HZ = 27_000_000
) (
    input  logic       clk,
    output logic [5:0] led
);
  localparam int TICKS = CLK_HZ / 4;

  logic [$clog2(TICKS)-1:0] div = '0;
  logic [5:0] count = '0;

  always_ff @(posedge clk) begin
    if (div == TICKS - 1) begin
      div   <= '0;
      count <= count + 1'b1;
    end else begin
      div <= div + 1'b1;
    end
  end

  assign led = ~count;
endmodule
"""

CONSTRAINTS_CST = """\
// Tang Nano 9K: 27 MHz clock, six user LEDs (active low).
IO_LOC "clk" 52;
IO_PORT "clk" IO_TYPE=LVCMOS33 PULL_MODE=UP;

IO_LOC "led[0]" 10;
IO_LOC "led[1]" 11;
IO_LOC "led[2]" 13;
IO_LOC "led[3]" 14;
IO_LOC "led[4]" 15;
IO_LOC "led[5]" 16;
IO_PORT "led[0]" IO_TYPE=LVCMOS18 DRIVE=8;
IO_PORT "led[1]" IO_TYPE=LVCMOS18 DRIVE=8;
IO_PORT "led[2]" IO_TYPE=LVCMOS18 DRIVE=8;
IO_PORT "led[3]" IO_TYPE=LVCMOS18 DRIVE=8;
IO_PORT "led[4]" IO_TYPE=LVCMOS18 DRIVE=8;
IO_PORT "led[5]" IO_TYPE=LVCMOS18 DRIVE=8;
"""

TOP_REL = "rtl/top.sv"
CONSTRAINTS_REL = f"{DEFAULT_BOARD}.cst"


@dataclass(frozen=True)
class ScaffoldFile:
    relpath: str
    content: str


@dataclass(frozen=True)
class ScaffoldPlan:
    cfg: ProjectConfig
    files: tuple[ScaffoldFile, ...]

    def conflicts(self, root: Path) -> list[Path]:
        return [root / f.relpath for f in self.files if (root / f.relpath).exists()]


def plan(root: Path, *, board: str = DEFAULT_BOARD) -> ScaffoldPlan:
    cfg = ProjectConfig(
        root=root.resolve(),
        board=board,
        top="top",
        sources=[TOP_REL],
        constraints=CONSTRAINTS_REL,
    )
    files = (
        ScaffoldFile(TOP_REL, TOP_SV),
        ScaffoldFile(CONSTRAINTS_REL, CONSTRAINTS_CST),
        ScaffoldFile("shepherd.toml", dump(cfg)),
    )
    return ScaffoldPlan(cfg=cfg, files=files)


def write(root: Path, scaffold: ScaffoldPlan) -> None:
    root = root.resolve()
    for item in scaffold.files:
        path = root / item.relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(item.content)
