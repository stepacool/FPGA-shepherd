# FPGA Shepherd

Shepherd speeds up adoption of complex chips like **FPGAs** (field-programmable gate arrays), so getting real hardware into the loop for **physical AI** is simpler.

You bring the design. Shepherd helps with setup, build, board bring-up, and figuring out what went wrong.

**v0 board:** Tang Nano 9K only.

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

If the board or toolchain looks wrong: `shepherd doctor --fix`.

For AI-assisted `explain` / `ask`, set `META_API_KEY`.

## Status

Early development, CLI first, then an optional UI. Working now: `shepherd build` / `shepherd upload` (Verilog / SystemVerilog), `--dry-run`, `--show-backend`, `--json`, `-v`, run history in `.shepherd/shepherd.db`. Progress: [CLI epic](https://github.com/FrankP89/FPGA-shepherd/issues/18).

## Develop

```bash
uv sync
uv run pytest
uv run shepherd -C examples/blinky_sv build      # needs the toolchain; see `--dry-run` otherwise
```

Build backend: [apio](https://fpgawars.github.io/apio/docs) (FPGAwars). You don’t need to install or learn it separately.
