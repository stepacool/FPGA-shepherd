# Shepherd control room (`web/`)

Next.js UI that **reads** `.shepherd/shepherd.db` and **spawns** `uv run shepherd …`. No FastAPI.

See [`docs/ui-spawn.md`](../docs/ui-spawn.md) for the spawn/cancel contract.

## Setup

Needs **Node ≥ 20** (this machine: `nvm use 20`).

```bash
# recommended: first-time install + build + serve (port 3010)
uv run shepherd ui -P examples/blinky_sv
uv run shepherd ui stop
uv run shepherd ui restart -P examples/blinky_sv
```

Or manually:

```bash
cd web
npm install && npm run build && npm start
```

Open [http://localhost:3010](http://localhost:3010) — path starts empty (commands disabled until you Open / New / Browse a project). Pass `?project=/abs/path` or `shepherd ui -P …` to pre-select one.
Override with `shepherd ui --port <port>` or `npm start -- -p <port>`.

On first `shepherd ui`, missing `node_modules` / `.next` triggers `npm install` and `npm run build` (wait ~1 minute).

## Stack

- Next.js App Router + TypeScript
- `better-sqlite3` (server-only, Node runtime)
- Tailwind for layout
