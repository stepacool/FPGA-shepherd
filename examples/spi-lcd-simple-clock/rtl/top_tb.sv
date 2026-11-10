// Smoke testbench for the SPI LCD clock (not synthesised; *_tb is ignored by build).
// Tiny CLK_HZ so ST7789 power-on waits finish quickly in simulation.
`timescale 1ns / 1ps
module top_tb;
  logic clk = 0;
  logic resetn = 0;
  logic lcd_resetn, lcd_clk, lcd_cs, lcd_rs, lcd_data;

  always #5 clk = ~clk;

  top #(
      .CLK_HZ(200)
  ) dut (
      .clk(clk),
      .resetn(resetn),
      .lcd_resetn(lcd_resetn),
      .lcd_clk(lcd_clk),
      .lcd_cs(lcd_cs),
      .lcd_rs(lcd_rs),
      .lcd_data(lcd_data)
  );

  initial begin
    $dumpvars(0, top_tb);
    repeat (5) @(posedge clk);
    resetn = 1'b1;
    // Cover reset → prepare → wakeup → snooze → init start (scaled waits).
    repeat (800) @(posedge clk);
    $finish;
  end
endmodule
