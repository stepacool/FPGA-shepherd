// Simple smoke testbench for blinky (not synthesised; *_tb is ignored by build).
// Use $dumpvars only — the backend sets the VCD path via vvp -dumpfile=.
`timescale 1ns / 1ps
module blinky_tb;
  logic clk = 0;
  logic [5:0] led;
  always #5 clk = ~clk;
  blinky #(.CLK_HZ(100)) dut (.clk(clk), .led(led));
  initial begin
    $dumpvars(0, blinky_tb);
    repeat (200) @(posedge clk);
    $finish;
  end
endmodule
