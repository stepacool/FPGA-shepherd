// Simple HH:MM:SS clock on the Tang Nano 9K plug-in SPI LCD (ST7789, 135x240).
// Screen sits on the board's 8-pin SPI LCD connector — no jumper GPIO wiring.
// Init sequence adapted from examples/spi_lcd_lines / Sipeed spi_lcd demo.
// INIT_* macros come from rtl/wall_time.sv (run stamp_wall_time.py before build).
module top #(
    parameter int CLK_HZ       = 27_000_000,
    parameter int INIT_HOURS   = `INIT_HOURS,
    parameter int INIT_MINUTES = `INIT_MINUTES,
    parameter int INIT_SECONDS = `INIT_SECONDS
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
  // MADCTL 0x70 window is 240 wide x 135 tall in write order.
  localparam int LCD_W = 240;
  localparam int LCD_H = 135;
  localparam int PIXEL_COUNT = LCD_W * LCD_H;

  localparam int CNT_100MS = CLK_HZ / 10;
  localparam int CNT_120MS = (CLK_HZ * 12) / 100;
  localparam int CNT_200MS = CLK_HZ / 5;

  localparam logic [3:0] ST_RESET   = 4'd0;
  localparam logic [3:0] ST_PREPARE = 4'd1;
  localparam logic [3:0] ST_WAKEUP  = 4'd2;
  localparam logic [3:0] ST_SNOOZE  = 4'd3;
  localparam logic [3:0] ST_INIT    = 4'd4;
  localparam logic [3:0] ST_FILL    = 4'd5;

  // 4x scaled 5x7 glyphs → 20x28 inside a 24-wide cell. Centered HH:MM:SS.
  localparam int CELL_W  = 24;
  localparam int GLYPH_W = 20;
  localparam int GLYPH_H = 28;
  localparam int START_X = (LCD_W - 8 * CELL_W) / 2;  // 24
  localparam int START_Y = (LCD_H - GLYPH_H) / 2;     // 53
  localparam int END_X   = START_X + 8 * CELL_W;      // 216
  localparam int END_Y   = START_Y + GLYPH_H;          // 81

  localparam logic [15:0] COL_FG = 16'hFFFF;  // white
  localparam logic [15:0] COL_BG = 16'h10A2;  // dark blue

  // 5x7 column-major (LSB = top). ch 0-9 digits, 10 colon, else blank.
  function automatic logic [6:0] font5x7(
      input logic [3:0] ch,
      input logic [2:0] col
  );
    begin
      case ({ch, col})
        {4'd0, 3'd0}: font5x7 = 7'h3E;
        {4'd0, 3'd1}: font5x7 = 7'h51;
        {4'd0, 3'd2}: font5x7 = 7'h49;
        {4'd0, 3'd3}: font5x7 = 7'h45;
        {4'd0, 3'd4}: font5x7 = 7'h3E;

        {4'd1, 3'd1}: font5x7 = 7'h42;
        {4'd1, 3'd2}: font5x7 = 7'h7F;
        {4'd1, 3'd3}: font5x7 = 7'h40;

        {4'd2, 3'd0}: font5x7 = 7'h42;
        {4'd2, 3'd1}: font5x7 = 7'h61;
        {4'd2, 3'd2}: font5x7 = 7'h51;
        {4'd2, 3'd3}: font5x7 = 7'h49;
        {4'd2, 3'd4}: font5x7 = 7'h46;

        {4'd3, 3'd0}: font5x7 = 7'h21;
        {4'd3, 3'd1}: font5x7 = 7'h41;
        {4'd3, 3'd2}: font5x7 = 7'h45;
        {4'd3, 3'd3}: font5x7 = 7'h4B;
        {4'd3, 3'd4}: font5x7 = 7'h31;

        {4'd4, 3'd0}: font5x7 = 7'h18;
        {4'd4, 3'd1}: font5x7 = 7'h14;
        {4'd4, 3'd2}: font5x7 = 7'h12;
        {4'd4, 3'd3}: font5x7 = 7'h7F;
        {4'd4, 3'd4}: font5x7 = 7'h10;

        {4'd5, 3'd0}: font5x7 = 7'h27;
        {4'd5, 3'd1}: font5x7 = 7'h45;
        {4'd5, 3'd2}: font5x7 = 7'h45;
        {4'd5, 3'd3}: font5x7 = 7'h45;
        {4'd5, 3'd4}: font5x7 = 7'h39;

        {4'd6, 3'd0}: font5x7 = 7'h3C;
        {4'd6, 3'd1}: font5x7 = 7'h4A;
        {4'd6, 3'd2}: font5x7 = 7'h49;
        {4'd6, 3'd3}: font5x7 = 7'h49;
        {4'd6, 3'd4}: font5x7 = 7'h30;

        {4'd7, 3'd0}: font5x7 = 7'h01;
        {4'd7, 3'd1}: font5x7 = 7'h71;
        {4'd7, 3'd2}: font5x7 = 7'h09;
        {4'd7, 3'd3}: font5x7 = 7'h05;
        {4'd7, 3'd4}: font5x7 = 7'h03;

        {4'd8, 3'd0}: font5x7 = 7'h36;
        {4'd8, 3'd1}: font5x7 = 7'h49;
        {4'd8, 3'd2}: font5x7 = 7'h49;
        {4'd8, 3'd3}: font5x7 = 7'h49;
        {4'd8, 3'd4}: font5x7 = 7'h36;

        {4'd9, 3'd0}: font5x7 = 7'h06;
        {4'd9, 3'd1}: font5x7 = 7'h49;
        {4'd9, 3'd2}: font5x7 = 7'h49;
        {4'd9, 3'd3}: font5x7 = 7'h29;
        {4'd9, 3'd4}: font5x7 = 7'h1E;

        {4'd10, 3'd1}: font5x7 = 7'h36;
        {4'd10, 3'd2}: font5x7 = 7'h36;

        default: font5x7 = 7'h00;
      endcase
    end
  endfunction

  function automatic logic [3:0] tens_digit6(input logic [5:0] v);
    begin
      if (v >= 6'd50)      tens_digit6 = 4'd5;
      else if (v >= 6'd40) tens_digit6 = 4'd4;
      else if (v >= 6'd30) tens_digit6 = 4'd3;
      else if (v >= 6'd20) tens_digit6 = 4'd2;
      else if (v >= 6'd10) tens_digit6 = 4'd1;
      else                 tens_digit6 = 4'd0;
    end
  endfunction

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
    init_cmd[59] = 9'h02A;
    init_cmd[60] = 9'h100;
    init_cmd[61] = 9'h128;
    init_cmd[62] = 9'h101;
    init_cmd[63] = 9'h117;
    init_cmd[64] = 9'h02B;
    init_cmd[65] = 9'h100;
    init_cmd[66] = 9'h135;
    init_cmd[67] = 9'h100;
    init_cmd[68] = 9'h1BB;
    init_cmd[69] = 9'h02C;
  end

  // ---- wall-clock (starts at INIT_*; no RTC, so update params before upload) ----
  localparam int SEC_DIV_W = $clog2(CLK_HZ);
  logic [SEC_DIV_W-1:0] sec_div = '0;
  logic [4:0] hours   = 5'(INIT_HOURS);
  logic [5:0] minutes = 6'(INIT_MINUTES);
  logic [5:0] seconds = 6'(INIT_SECONDS);

  always_ff @(posedge clk) begin
    if (sec_div == SEC_DIV_W'(CLK_HZ - 1)) begin
      sec_div <= '0;
      if (seconds == 6'd59) begin
        seconds <= 6'd0;
        if (minutes == 6'd59) begin
          minutes <= 6'd0;
          if (hours == 5'd23)
            hours <= 5'd0;
          else
            hours <= hours + 5'd1;
        end else begin
          minutes <= minutes + 6'd1;
        end
      end else begin
        seconds <= seconds + 6'd1;
      end
    end else begin
      sec_div <= sec_div + 1'b1;
    end
  end

  logic [3:0] g0, g1, g2, g3, g4, g5, g6, g7;
  logic [3:0] hours_tens, min_tens, sec_tens;
  always_comb begin
    if (hours >= 5'd20)      hours_tens = 4'd2;
    else if (hours >= 5'd10) hours_tens = 4'd1;
    else                     hours_tens = 4'd0;
    min_tens = tens_digit6(minutes);
    sec_tens = tens_digit6(seconds);

    g0 = hours_tens;
    g1 = 4'(hours - (hours_tens * 4'd10));
    g2 = seconds[0] ? 4'd11 : 4'd10;
    g3 = min_tens;
    g4 = 4'(minutes - (min_tens * 4'd10));
    g5 = seconds[0] ? 4'd11 : 4'd10;
    g6 = sec_tens;
    g7 = 4'(seconds - (sec_tens * 4'd10));
  end

  // Scan position for the current pixel being shifted out.
  logic [7:0] pix_x;
  logic [7:0] pix_y;

  logic [7:0] rel_x;
  logic [2:0] slot;
  logic [7:0] slot_base;
  logic [4:0] local_x;
  logic [4:0] local_y;
  logic [3:0] ch;
  logic [6:0] font_bits;
  logic       on_pixel;
  logic [15:0] pixel;

  always_comb begin
    rel_x     = 8'd0;
    slot      = 3'd0;
    slot_base = 8'd0;
    local_x   = 5'd0;
    local_y   = 5'd0;
    ch        = 4'd11;
    font_bits = 7'h00;
    on_pixel  = 1'b0;
    pixel     = COL_BG;

    if (pix_x >= 8'(START_X) && pix_x < 8'(END_X) &&
        pix_y >= 8'(START_Y) && pix_y < 8'(END_Y)) begin
      rel_x = pix_x - 8'(START_X);
      if (rel_x < 8'd24)      slot = 3'd0;
      else if (rel_x < 8'd48) slot = 3'd1;
      else if (rel_x < 8'd72) slot = 3'd2;
      else if (rel_x < 8'd96) slot = 3'd3;
      else if (rel_x < 8'd120) slot = 3'd4;
      else if (rel_x < 8'd144) slot = 3'd5;
      else if (rel_x < 8'd168) slot = 3'd6;
      else                     slot = 3'd7;

      // slot * 24 = slot*16 + slot*8
      slot_base = {slot, 4'b0000} + {1'b0, slot, 3'b000};
      local_x   = 5'(rel_x - slot_base);
      local_y   = 5'(pix_y - 8'(START_Y));

      case (slot)
        3'd0: ch = g0;
        3'd1: ch = g1;
        3'd2: ch = g2;
        3'd3: ch = g3;
        3'd4: ch = g4;
        3'd5: ch = g5;
        3'd6: ch = g6;
        default: ch = g7;
      endcase

      if (local_x < 5'(GLYPH_W)) begin
        font_bits = font5x7(ch, local_x[4:2]);  // /4
        on_pixel  = font_bits[local_y[4:2]];    // /4
      end
      pixel = on_pixel ? COL_FG : COL_BG;
    end
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

  assign lcd_clk    = ~clk;
  assign lcd_cs     = lcd_cs_r;
  assign lcd_rs     = lcd_rs_r;
  assign lcd_resetn = lcd_reset_r;
  assign lcd_data   = spi_byte[7];

  always_ff @(posedge clk or negedge resetn) begin
    if (!resetn) begin
      state       <= ST_RESET;
      clk_cnt     <= '0;
      cmd_index   <= '0;
      bit_loop    <= '0;
      pixel_cnt   <= '0;
      pix_x       <= '0;
      pix_y       <= '0;
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
            pix_x     <= '0;
            pix_y     <= '0;
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
          // Stream frames forever so the clock digits keep updating.
          if (bit_loop == 5'd0) begin
            lcd_cs_r <= 1'b0;
            lcd_rs_r <= 1'b1;
            spi_byte <= pixel[15:8];
            bit_loop <= 5'd1;
          end else if (bit_loop == 5'd8) begin
            spi_byte <= pixel[7:0];
            bit_loop <= 5'd9;
          end else if (bit_loop == 5'd16) begin
            lcd_cs_r <= 1'b1;
            lcd_rs_r <= 1'b1;
            bit_loop <= '0;
            if (pixel_cnt == 16'(PIXEL_COUNT - 1)) begin
              pixel_cnt <= '0;
              pix_x     <= '0;
              pix_y     <= '0;
            end else begin
              pixel_cnt <= pixel_cnt + 1'b1;
              if (pix_x == 8'(LCD_W - 1)) begin
                pix_x <= '0;
                pix_y <= pix_y + 1'b1;
              end else begin
                pix_x <= pix_x + 1'b1;
              end
            end
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
