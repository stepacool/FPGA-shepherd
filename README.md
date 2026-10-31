# FPGA Shepherd

**AI-assisted FPGA / digital-design engineer tool** for people who already write **register-transfer level (RTL)**. You bring the design; Shepherd handles adapters, toolchain plumbing, build/upload, and failure diagnosis.

> You write the RTL — in whatever **hardware description language (HDL)** you use. Shepherd picks the right HDL adapter, builds and flashes your board, and when something breaks it tells you why and how to fix it.

**Not** a “describe an app in English and we invent the design” product. Audience: competent FPGA engineers.

**v0 board:** Tang Nano 9K only.

## Docs

- [`PLAN.md`](PLAN.md) — product architecture (CLI, apio backend, agents, checkpoints, SQLite events)
- [`PLAN_UI.md`](PLAN_UI.md) — optional Next.js UI (reads the same SQLite DB; no FastAPI)

## How it works (short)

- **Shepherd** is the interface: `shepherd.toml`, Shepherd commands, Shepherd verdicts
- Under the hood it drives **[apio](https://fpgawars.github.io/apio/docs)** (toolchain, boards, synth / place-and-route / program). Default UX hides apio; power users can use `--show-backend`
- Run state: **SQLite** (`.shepherd/shepherd.db`) + per-step logs — **no `run.json`**
- Optional web UI polls that DB and can spawn `shepherd … --yes` (cancel via process id)

## Status

Planning / early scaffolding. Implementation order is **CLI first**, then UI.

## Intended quickstart (once implemented)

```bash
cd FPGA-shepherd
uv sync
cp .env.example .env        # set META_API_KEY for AI explain/ask
uv run shepherd doctor      # may need internet the first time (clear error if offline)
cd examples/blinky_sv && uv run shepherd upload
```

UI (after CLI works): see [`PLAN_UI.md`](PLAN_UI.md).

## Credit

Build backend: [apio](https://fpgawars.github.io/apio/docs) (FPGAwars). We respect its license and credit it in docs; it is an implementation detail of the default workflow, not something users must install or learn separately.
