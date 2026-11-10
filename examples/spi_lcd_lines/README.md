# SPI LCD (ST7789) on Tang Nano 9K

Plug the Sipeed **1.14" SPI LCD** into the board’s 8-pin SPI LCD connector (no jumper wiring). This example initializes the ST7789 and fills the panel with blue / green / red color bars.

## Run

```bash
uv run shepherd -P examples/spi_lcd_st7789 build
uv run shepherd -P examples/spi_lcd_st7789 upload
```

Hold the on-board button (pin 4 / `resetn`) during power-up if you need a clean restart of the init sequence after upload.

## Docs

- [Sipeed SPI LCD wiki](https://wiki.sipeed.com/hardware/zh/tang/Tang-Nano-9K/examples/spi_lcd/spi_lcd.html)
- Reference HDL: [sipeed/TangNano-9K-example `spi_lcd`](https://github.com/sipeed/TangNano-9K-example/tree/main/spi_lcd)
