// Counts up on the six on-board LEDs of a Tang Nano 9K (LEDs are active low).
module blinky #(
    parameter int CLK_HZ = 27_000_000
) (
    input  logic       clk,
    output logic [5:0] led
);
  localparam int TICKS = CLK_HZ / 4;  // advance 4 times per second

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
