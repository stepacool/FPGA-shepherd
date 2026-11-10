// Drive the Sipeed 1.14" 135x240 SPI LCD (ST7789V3) on the Tang Nano 9K
// SPI LCD connector. After init, fill the panel with RGB565 color bars
// (blue / green / red). Adapted from the Sipeed TangNano-9K-example spi_lcd
// demo, with real power-on delays for hardware (upstream left sim-speed delays
// as the default path).
//
// Docs: https://wiki.sipeed.com/hardware/zh/tang/Tang-Nano-9K/examples/spi_lcd/spi_lcd.html
module spi_lcd_st7789 #(
    parameter int CLK_HZ = 27_000_000
) (
    input  logic clk,
    input  logic resetn,

    output logic lcd_resetn,
    output logic lcd_clk,
    output logic lcd_cs,
    output logic lcd_rs,
    output logic lcd_data
);

  localparam int MAX_CMDS = 69;
  localparam int PIXEL_COUNT = 135 * 240;  // 32400

  // Real ST7789 power-on waits (upstream example used ~27-cycle stubs unless MODELTECH).
  localparam int CNT_100MS = CLK_HZ / 10;
  localparam int CNT_120MS = (CLK_HZ * 12) / 100;
  localparam int CNT_200MS = CLK_HZ / 5;

  localparam logic [3:0] ST_RESET   = 4'd0;
  localparam logic [3:0] ST_PREPARE = 4'd1;
  localparam logic [3:0] ST_WAKEUP  = 4'd2;
  localparam logic [3:0] ST_SNOOZE  = 4'd3;
  localparam logic [3:0] ST_INIT    = 4'd4;
  localparam logic [3:0] ST_FILL    = 4'd5;

  // Bit 8 = 0 command / 1 data; bits [7:0] = payload (Sipeed spi_lcd init table).
  logic [8:0] init_cmd [0:MAX_CMDS];
  initial begin
    init_cmd[0]  = 9'h036;
    init_cmd[1]  = 9'h170;
    init_cmd[2]  = 9'h03A;
    init_cmd[3]  = 9'h105;
    init_cmd[4]  = 9'h0B2;
    init_cmd[5]  = 9'h10C;
    init_cmd[6]  = 9'h10C;
    init_cmd[7]  = 9'h100;
    init_cmd[8]  = 9'h133;
    init_cmd[9]  = 9'h133;
    init_cmd[10] = 9'h0B7;
    init_cmd[11] = 9'h135;
    init_cmd[12] = 9'h0BB;
    init_cmd[13] = 9'h119;
    init_cmd[14] = 9'h0C0;
    init_cmd[15] = 9'h12C;
    init_cmd[16] = 9'h0C2;
    init_cmd[17] = 9'h101;
    init_cmd[18] = 9'h0C3;
    init_cmd[19] = 9'h112;
    init_cmd[20] = 9'h0C4;
    init_cmd[21] = 9'h120;
    init_cmd[22] = 9'h0C6;
    init_cmd[23] = 9'h10F;
    init_cmd[24] = 9'h0D0;
    init_cmd[25] = 9'h1A4;
    init_cmd[26] = 9'h1A1;
    init_cmd[27] = 9'h0E0;
    init_cmd[28] = 9'h1D0;
    init_cmd[29] = 9'h104;
    init_cmd[30] = 9'h10D;
    init_cmd[31] = 9'h111;
    init_cmd[32] = 9'h113;
    init_cmd[33] = 9'h12B;
    init_cmd[34] = 9'h13F;
    init_cmd[35] = 9'h154;
    init_cmd[36] = 9'h14C;
    init_cmd[37] = 9'h118;
    init_cmd[38] = 9'h10D;
    init_cmd[39] = 9'h10B;
    init_cmd[40] = 9'h11F;
    init_cmd[41] = 9'h123;
    init_cmd[42] = 9'h0E1;
    init_cmd[43] = 9'h1D0;
    init_cmd[44] = 9'h104;
    init_cmd[45] = 9'h10C;
    init_cmd[46] = 9'h111;
    init_cmd[47] = 9'h113;
    init_cmd[48] = 9'h12C;
    init_cmd[49] = 9'h13F;
    init_cmd[50] = 9'h144;
    init_cmd[51] = 9'h151;
    init_cmd[52] = 9'h12F;
    init_cmd[53] = 9'h11F;
    init_cmd[54] = 9'h11F;
    init_cmd[55] = 9'h120;
    init_cmd[56] = 9'h123;
    init_cmd[57] = 9'h021;
    init_cmd[58] = 9'h029;
    init_cmd[59] = 9'h02A;  // column address
    init_cmd[60] = 9'h100;
    init_cmd[61] = 9'h128;
    init_cmd[62] = 9'h101;
    init_cmd[63] = 9'h117;
    init_cmd[64] = 9'h02B;  // row address
    init_cmd[65] = 9'h100;
    init_cmd[66] = 9'h135;
    init_cmd[67] = 9'h100;
    init_cmd[68] = 9'h1BB;
    init_cmd[69] = 9'h02C;  // memory write
  end

  logic [3:0] state;
  logic [6:0] cmd_index;
  logic [31:0] clk_cnt;
  logic [4:0] bit_loop;
  logic [15:0] pixel_cnt;
  logic [7:0] spi_byte;

  logic lcd_cs_r;
  logic lcd_rs_r;
  logic lcd_reset_r;

  // Free-running SPI clock (inverted board clock), matching the Sipeed demo.
  assign lcd_clk    = ~clk;
  assign lcd_cs     = lcd_cs_r;
  assign lcd_rs     = lcd_rs_r;
  assign lcd_resetn = lcd_reset_r;
  assign lcd_data   = spi_byte[7];

  // Three horizontal bars: blue, green, red (RGB565).
  logic [15:0] pixel;
  always_comb begin
    if (pixel_cnt >= 16'(PIXEL_COUNT * 2 / 3))
      pixel = 16'hF800;  // red
    else if (pixel_cnt >= 16'(PIXEL_COUNT / 3))
      pixel = 16'h07E0;  // green
    else
      pixel = 16'h001F;  // blue
  end

  always_ff @(posedge clk or negedge resetn) begin
    if (!resetn) begin
      state       <= ST_RESET;
      clk_cnt     <= '0;
      cmd_index   <= '0;
      bit_loop    <= '0;
      pixel_cnt   <= '0;
      lcd_cs_r    <= 1'b1;
      lcd_rs_r    <= 1'b1;
      lcd_reset_r <= 1'b0;
      spi_byte    <= 8'hFF;
    end else begin
      case (state)
        ST_RESET: begin
          lcd_reset_r <= 1'b0;
          if (clk_cnt == 32'(CNT_100MS - 1)) begin
            clk_cnt     <= '0;
            lcd_reset_r <= 1'b1;
            state       <= ST_PREPARE;
          end else begin
            clk_cnt <= clk_cnt + 1'b1;
          end
        end

        ST_PREPARE: begin
          if (clk_cnt == 32'(CNT_200MS - 1)) begin
            clk_cnt  <= '0;
            bit_loop <= '0;
            state    <= ST_WAKEUP;
          end else begin
            clk_cnt <= clk_cnt + 1'b1;
          end
        end

        ST_WAKEUP: begin
          // Sleep-out (0x11), one SPI byte bit-bang.
          if (bit_loop == 5'd0) begin
            lcd_cs_r <= 1'b0;
            lcd_rs_r <= 1'b0;
            spi_byte <= 8'h11;
            bit_loop <= 5'd1;
          end else if (bit_loop == 5'd8) begin
            lcd_cs_r <= 1'b1;
            lcd_rs_r <= 1'b1;
            bit_loop <= '0;
            clk_cnt  <= '0;
            state    <= ST_SNOOZE;
          end else begin
            spi_byte <= {spi_byte[6:0], 1'b1};
            bit_loop <= bit_loop + 1'b1;
          end
        end

        ST_SNOOZE: begin
          if (clk_cnt == 32'(CNT_120MS - 1)) begin
            clk_cnt   <= '0;
            cmd_index <= '0;
            bit_loop  <= '0;
            state     <= ST_INIT;
          end else begin
            clk_cnt <= clk_cnt + 1'b1;
          end
        end

        ST_INIT: begin
          if (cmd_index == 7'(MAX_CMDS + 1)) begin
            bit_loop  <= '0;
            pixel_cnt <= '0;
            state     <= ST_FILL;
          end else if (bit_loop == 5'd0) begin
            lcd_cs_r <= 1'b0;
            lcd_rs_r <= init_cmd[cmd_index][8];
            spi_byte <= init_cmd[cmd_index][7:0];
            bit_loop <= 5'd1;
          end else if (bit_loop == 5'd8) begin
            lcd_cs_r  <= 1'b1;
            lcd_rs_r  <= 1'b1;
            bit_loop  <= '0;
            cmd_index <= cmd_index + 1'b1;
          end else begin
            spi_byte <= {spi_byte[6:0], 1'b1};
            bit_loop <= bit_loop + 1'b1;
          end
        end

        ST_FILL: begin
          if (pixel_cnt == 16'(PIXEL_COUNT)) begin
            lcd_cs_r <= 1'b1;
            lcd_rs_r <= 1'b1;
          end else if (bit_loop == 5'd0) begin
            lcd_cs_r <= 1'b0;
            lcd_rs_r <= 1'b1;
            spi_byte <= pixel[15:8];
            bit_loop <= 5'd1;
          end else if (bit_loop == 5'd8) begin
            spi_byte <= pixel[7:0];
            bit_loop <= 5'd9;
          end else if (bit_loop == 5'd16) begin
            lcd_cs_r  <= 1'b1;
            lcd_rs_r  <= 1'b1;
            bit_loop  <= '0;
            pixel_cnt <= pixel_cnt + 1'b1;
          end else begin
            spi_byte <= {spi_byte[6:0], 1'b1};
            bit_loop <= bit_loop + 1'b1;
          end
        end

        default: state <= ST_RESET;
      endcase
    end
  end
endmodule
