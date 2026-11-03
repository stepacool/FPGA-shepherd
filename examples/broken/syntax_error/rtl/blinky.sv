module blinky(input clk, output led);
  // intentional syntax error
  always_ff @(posedge clk begin
    led <= ~led;
  end
endmodule
