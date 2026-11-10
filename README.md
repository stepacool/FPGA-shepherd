# FPGA Shepherd

**▶ YOUTUBE DEMO: https://youtu.be/yWx52wcJTa8**

[![Watch the demo](https://img.youtube.com/vi/yWx52wcJTa8/hqdefault.jpg)](https://youtu.be/yWx52wcJTa8)

[![ci](https://github.com/FrankP89/FPGA-shepherd/actions/workflows/ci.yml/badge.svg)](https://github.com/FrankP89/FPGA-shepherd/actions/workflows/ci.yml)

Shepherd speeds up adoption of complex chips like **FPGAs** (field-programmable gate arrays), so getting real hardware into the loop for **physical AI** is simpler.

You bring the design. Shepherd helps with setup, build, board bring-up, and figuring out what went wrong.

**v0 board:** Tang Nano 9K only.

Glossary: [Acronyms](ACRONYMS.md).

## Journey

<table>
  <tr>
    <td width="9%" align="right" valign="middle"><em>Stage</em></td>
    <td width="12%" align="center"><b>System setup</b></td>
    <td width="2%" align="center"><b>→</b></td>
    <td width="12%" align="center"><b>Define project</b></td>
    <td width="2%" align="center"><b>→</b></td>
    <td width="12%" align="center"><b>Adapt HDL</b></td>
    <td width="2%" align="center"><b>→</b></td>
    <td width="12%" align="center"><b>Synth / P&amp;R / pack</b></td>
    <td width="2%" align="center"><b>→</b></td>
    <td width="12%" align="center"><b>Program board</b></td>
    <td width="2%" align="center"><b>→</b></td>
    <td width="12%" align="center"><b>Debug / diagnose</b></td>
    <td width="2%" align="center"><b>→</b></td>
    <td width="12%" align="center"><b>Live view</b><br/><em>(optional)</em></td>
  </tr>
  <tr>
    <td width="9%" align="right" valign="top"><em>Commands</em></td>
    <td width="12%" align="center" valign="top"><code>install.sh</code></td>
    <td width="2%"></td>
    <td width="12%" align="center" valign="top"><code>shepherd init</code></td>
    <td width="2%"></td>
    <td width="12%" align="center" valign="top"><code>shepherd build</code><br/><em>(adapter step)</em></td>
    <td width="2%"></td>
    <td width="12%" align="center" valign="top"><code>shepherd build</code></td>
    <td width="2%"></td>
    <td width="12%" align="center" valign="top"><code>shepherd upload</code></td>
    <td width="2%"></td>
    <td width="12%" align="center" valign="top"><code>shepherd explain</code><br/><code>shepherd ask</code></td>
    <td width="2%"></td>
    <td width="12%" align="center" valign="top"><code>shepherd ui</code></td>
  </tr>
  <tr>
    <td width="9%" align="right" valign="top"><em>Under the hood</em></td>
    <td width="12%" align="center" valign="top">uv + shepherd<br/>init → uv · apio pkgs</td>
    <td width="2%"></td>
    <td width="12%" align="center" valign="top"><code>shepherd.toml</code><br/>AdoptAgent</td>
    <td width="2%"></td>
    <td width="12%" align="center" valign="top">Verilog/SV passthrough<br/>Amaranth emit</td>
    <td width="2%"></td>
    <td width="12%" align="center" valign="top">apio · Yosys · nextpnr<br/>checkpoints</td>
    <td width="2%"></td>
    <td width="12%" align="center" valign="top">openFPGALoader<br/>Tang Nano 9K</td>
    <td width="2%"></td>
    <td width="12%" align="center" valign="top">VerifyAgent · signatures<br/>Meta Llama</td>
    <td width="2%"></td>
    <td width="12%" align="center" valign="top">Next.js · SQLite events<br/>watch / click-run</td>
  </tr>
</table>

If something fails in debug, fix the design and retry from adapt.

`shepherd ui` opens the live view anytime after the project exists (not only at the end).

## How to use

Not released yet. When it is:

```bash
curl -LsSf https://raw.githubusercontent.com/FrankP89/FPGA-shepherd/main/scripts/install.sh | sh

cd my-fpga-project
shepherd init
shepherd upload
```

Use `-P` / `--project` when the project is not the current directory:

```bash
shepherd build -P examples/blinky_sv
shepherd ask -P examples/blinky_sv "why are the LEDs active-low?"
```

If the board or toolchain looks wrong: `shepherd doctor --fix`.

For AI-assisted `explain` / `ask`, set `META_API_KEY`.

`sim` / `test` pick up sibling `*_tb.v` / `*_tb.sv` next to your sources automatically (you can still list them in `shepherd.toml`).

## Status

Early development. Working now: `init`, `doctor`, `build` / `upload`, `lint` / `sim` / `test` / `report`, `explain` / `ask`, Amaranth adapter, run history in `.shepherd/shepherd.db`, and a Next.js control room in `web/` (`shepherd ui` / `stop` / `restart`, Surfer waveforms after `sim`). Progress: [CLI epic](https://github.com/FrankP89/FPGA-shepherd/issues/18), [UI epic](https://github.com/FrankP89/FPGA-shepherd/issues/27). Spawn contract: [`docs/ui-spawn.md`](docs/ui-spawn.md).

## Develop

Prefer `uv run shepherd` from this repo so you are not on a stale PATH install:

```bash
uv sync
uv run pytest
uv run shepherd -P examples/blinky_sv build      # needs the toolchain; see `--dry-run` otherwise
uv run shepherd -P examples/blinky_sv sim
uv run shepherd -P examples/uart_amaranth build
uv run shepherd -P examples/spi_lcd_st7789 build  # Sipeed SPI LCD connector
```

Refresh the global `shepherd` on PATH from this checkout:

```bash
uv tool install --force --reinstall .
# or: SHEPHERD_SOURCE=. bash scripts/install.sh
```

Build backend: [apio](https://fpgawars.github.io/apio/docs) (FPGAwars). You don’t need to install or learn it separately.
