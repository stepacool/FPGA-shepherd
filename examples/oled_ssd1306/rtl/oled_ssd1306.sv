// Drive a 0.96" 128x64 SSD1306 OLED over 4-wire SPI on Tang Nano 9K GPIO.
// After init, stream a procedural checker pattern (no external image.hex).
// Init / SPI timing follow the Lushay Labs Tang Nano 9K OLED 101 article:
// https://learn.lushaylabs.com/tang-nano-9k-graphics/
module oled_ssd1306 #(
    parameter int CLK_HZ = 27_000_000,
    // ~370 ms power-settle / reset pulse width (Lushay default).
    parameter int STARTUP_WAIT = 10_000_000
) (
    input  logic clk,
    output logic oled_sclk,
    output logic oled_mosi,
    output logic oled_cs,
    output logic oled_dc,
    output logic oled_reset
);

  localparam int SETUP_INSTRUCTIONS = 23;

  localparam logic [2:0] ST_INIT_POWER          = 3'd0;
  localparam logic [2:0] ST_LOAD_INIT_CMD       = 3'd1;
  localparam logic [2:0] ST_SEND                = 3'd2;
  localparam logic [2:0] ST_CHECK_FINISHED_INIT = 3'd3;
  localparam logic [2:0] ST_LOAD_DATA           = 3'd4;

  logic [7:0] startup_cmd [0:SETUP_INSTRUCTIONS-1];
  initial begin
    startup_cmd[0]  = 8'hAE;  // display off
    startup_cmd[1]  = 8'h81;  // contrast
    startup_cmd[2]  = 8'h7F;
    startup_cmd[3]  = 8'hA6;  // normal (not inverted)
    startup_cmd[4]  = 8'h20;  // addressing mode
    startup_cmd[5]  = 8'h00;  // horizontal
    startup_cmd[6]  = 8'hC8;  // COM scan direction
    startup_cmd[7]  = 8'h40;  // start line
    startup_cmd[8]  = 8'hA1;  // segment remap
    startup_cmd[9]  = 8'hA8;  // mux ratio
    startup_cmd[10] = 8'h3F;  // 64-1
    startup_cmd[11] = 8'hD3;  // display offset
    startup_cmd[12] = 8'h00;
    startup_cmd[13] = 8'hD5;  // clock divide
    startup_cmd[14] = 8'h80;
    startup_cmd[15] = 8'hD9;  // precharge
    startup_cmd[16] = 8'h22;
    startup_cmd[17] = 8'hDB;  // VCOMH
    startup_cmd[18] = 8'h20;
    startup_cmd[19] = 8'h8D;  // charge pump
    startup_cmd[20] = 8'h14;  // enable
    startup_cmd[21] = 8'hA4;  // resume RAM
    startup_cmd[22] = 8'hAF;  // display on
  end

  logic [2:0] state = ST_INIT_POWER;
  logic [31:0] counter = '0;
  logic [4:0] cmd_index = '0;
  logic [3:0] bit_number = '0;
  logic [9:0] pixel_counter = '0;
  logic [7:0] data_to_send = '0;

  logic sclk_r = 1'b1;
  logic mosi_r = 1'b0;
  logic cs_r = 1'b1;
  logic dc_r = 1'b1;
  logic reset_r = 1'b1;

  assign oled_sclk  = sclk_r;
  assign oled_mosi  = mosi_r;
  assign oled_cs    = cs_r;
  assign oled_dc    = dc_r;
  assign oled_reset = reset_r;

  // 8x8 checker: each SSD1306 byte is one column of 8 vertical pixels.
  logic [7:0] pattern_byte;
  always_comb begin
    if (pixel_counter[3] ^ pixel_counter[7])
      pattern_byte = 8'hFF;
    else
      pattern_byte = 8'h00;
  end

  always_ff @(posedge clk) begin
    case (state)
      ST_INIT_POWER: begin
        counter <= counter + 1'b1;
        if (counter < 32'(STARTUP_WAIT))
          reset_r <= 1'b1;
        else if (counter < 32'(STARTUP_WAIT * 2))
          reset_r <= 1'b0;
        else if (counter < 32'(STARTUP_WAIT * 3))
          reset_r <= 1'b1;
        else begin
          state   <= ST_LOAD_INIT_CMD;
          counter <= '0;
        end
      end

      ST_LOAD_INIT_CMD: begin
        dc_r         <= 1'b0;
        data_to_send <= startup_cmd[cmd_index];
        bit_number   <= 4'd7;
        cs_r         <= 1'b0;
        state        <= ST_SEND;
      end

      ST_SEND: begin
        if (counter == 32'd0) begin
          sclk_r  <= 1'b0;
          mosi_r  <= data_to_send[bit_number];
          counter <= 32'd1;
        end else begin
          counter <= 32'd0;
          sclk_r  <= 1'b1;
          if (bit_number == 4'd0)
            state <= ST_CHECK_FINISHED_INIT;
          else
            bit_number <= bit_number - 1'b1;
        end
      end

      ST_CHECK_FINISHED_INIT: begin
        cs_r <= 1'b1;
        if (cmd_index == 5'(SETUP_INSTRUCTIONS - 1))
          state <= ST_LOAD_DATA;
        else begin
          cmd_index <= cmd_index + 1'b1;
          state     <= ST_LOAD_INIT_CMD;
        end
      end

      ST_LOAD_DATA: begin
        pixel_counter <= pixel_counter + 1'b1;
        cs_r          <= 1'b0;
        dc_r          <= 1'b1;
        bit_number    <= 4'd7;
        data_to_send  <= pattern_byte;
        state         <= ST_SEND;
      end

      default: state <= ST_INIT_POWER;
    endcase
  end
endmodule
