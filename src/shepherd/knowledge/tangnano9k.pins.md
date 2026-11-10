# Tang Nano 9K pin facts (diagnosis only)

These nets come from the public schematic / wiki. They are **not** a build-time pin registry.

| Net | Pin | Notes |
| --- | --- | --- |
| clk | 52 | 27 MHz oscillator |
| led[0] | 10 | active low |
| led[1] | 11 | active low |
| led[2] | 13 | active low |
| led[3] | 14 | active low |
| led[4] | 15 | active low |
| led[5] | 16 | active low |
| resetn | 4 | on-board button (active low); used by SPI LCD example |
| lcd_resetn | 47 | SPI LCD connector |
| lcd_cs | 48 | SPI LCD connector |
| lcd_rs | 49 | SPI LCD connector (DC / command vs data) |
| lcd_clk | 76 | SPI LCD connector |
| lcd_data | 77 | SPI LCD connector (MOSI) |
| oled_cs | 36 | jumper SSD1306 example (Lushay pin pick) |
| oled_dc | 39 | jumper SSD1306 example |
| oled_reset | 25 | jumper SSD1306 example |
| oled_mosi | 26 | jumper SSD1306 example |
| oled_sclk | 27 | jumper SSD1306 example |

UART / button nets vary by revision; confirm against the schematic before suggesting IO_LOC lines. SPI LCD connector nets match the Sipeed 1.14" ST7789 panel path. OLED nets above are example GPIOs, not a fixed board connector.
