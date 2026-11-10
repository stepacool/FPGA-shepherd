# 0.96" SSD1306 OLED (jumper SPI)

Drive a **128×64 SSD1306** OLED over 4-wire SPI using Tang Nano 9K GPIO jumpers. After init, the panel shows a black/white checker pattern.

This is separate from [`examples/spi_lcd_st7789`](../spi_lcd_st7789): that one plugs into the board’s SPI LCD connector.

## Wiring

| OLED pin | Board signal | FPGA pin |
| --- | --- | --- |
| GND | GND | — |
| VCC | 3.3 V | — |
| D0 / SCLK | `oled_sclk` | 27 |
| D1 / MOSI | `oled_mosi` | 26 |
| RES | `oled_reset` | 25 |
| DC | `oled_dc` | 39 |
| CS | `oled_cs` | 36 |

Use a 7-pin SSD1306 module in **4-wire SPI** mode.

## Run

```bash
uv run shepherd -P examples/oled_ssd1306 build
uv run shepherd -P examples/oled_ssd1306 upload
```

## Docs

- [Lushay Labs: Tang Nano 9K OLED Screen 101](https://learn.lushaylabs.com/tang-nano-9k-graphics/)
