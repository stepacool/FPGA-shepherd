# FPGA Shepherd

Shepherd speeds up adoption of complex chips like **field-programmable gate arrays (FPGAs)** — so getting real hardware into the loop for **physical AI** is simpler.

You bring the design. Shepherd helps with build, board bring-up, and figuring out what went wrong.

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

We use **`uv` only** (never `pip`). End users don’t hand-manage envs — **`shepherd init` runs `uv` internally**:

```bash
uv tool install fpga-shepherd   # once — installs the `shepherd` CLI via uv
cd my-fpga-project
shepherd init                   # project + deps (uv + toolchain; may need internet)
shepherd upload
```

Optional: set `META_API_KEY` for AI explain/ask. Repair path: `shepherd doctor --fix`.

Contributors in this repo: `uv sync` / `uv run` — see [`PLAN.md`](PLAN.md).

UI (after CLI works): see [`PLAN_UI.md`](PLAN_UI.md).

## Credit

Build backend: [apio](https://fpgawars.github.io/apio/docs) (FPGAwars). We respect its license and credit it in docs; it is an implementation detail of the default workflow, not something users must install or learn separately.
