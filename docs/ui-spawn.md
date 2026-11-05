# UI ↔ Shepherd spawn contract

How the Next.js control room (`web/`) starts and stops CLI runs. See also issue #28.

## Database

| Item | Path |
| --- | --- |
| Events DB | `<project>/.shepherd/shepherd.db` |
| Step logs | `<project>/.shepherd/runs/<run_id>/` |
| Lock | `<project>/.shepherd/lock` (`<pid> <run_id>`) |

Shepherd **writes**; the UI **reads** (poll) and **spawns** — no FastAPI.

## Spawn argv

```text
uv run --directory <repo-root> shepherd <command> [args…] --yes -P <abs-project> --run-id <id>
  cwd     = <abs-project>
  detached process group (Node `spawn(..., { detached: true })`)
  stdio   = ignore (no TTY → no hung prompts)
```

`--run-id` / `--yes` / `-P` are accepted **after** the subcommand (re-declared on each command for UI spawns).

- UI allocates `run-id` first so Cancel can bind before the first DB row.
- Always `--yes`.
- Optional `--show-backend` when Advanced is on.
- Allowed commands: `build`, `upload`, `verify`, `reset`, `doctor`, `explain`, `ask`, `sim`, `lint`, `test`, `report`.
- **Gate:** `upload` / `sim` / `test` / `report` require a prior successful `build` (or an on-disk `hardware.fs`). `verify` requires a prior successful `upload`. The UI also keeps session `Built` / `Uploaded` flags (off by default; cleared on fail or source change).
- **`reset`:** resets the FPGA (clears SRAM program on the board). Toolbar **Reset** button.
- **`ask wipe`:** wipes `.shepherd/shepherd.db` and `.shepherd/runs/` (Ask / explain / verify history). Keeps `.shepherd/build/` and `.shepherd/gen/`. Ask panel **Clear** control spawns `ask` with args `["wipe"]`. After success the UI resets the Ask Q+A.

Implementation: [`web/src/lib/spawnShepherd.ts`](../web/src/lib/spawnShepherd.ts).

## Cancel

1. Prefer `runs.pgid` (or `runs.pid`) from SQLite.
2. Else use the in-process pid recorded at spawn time.
3. `kill(-pgid, SIGTERM)`, then `SIGKILL` after ~2s.

## Lock

If `.shepherd/lock` names a live pid → UI returns **run already active** and does not spawn.

## Open the UI

```bash
uv run shepherd ui -P examples/blinky_sv   # start (port 3010); installs+builds web/ on first use
uv run shepherd ui stop                    # stop background npm start
uv run shepherd ui restart -P examples/blinky_sv
# override port: shepherd ui --port 3000
```

Node ≥ 20 recommended (`nvm use 20`). First run may take ~1 minute (`npm install` + `npm run build`).
Pid recorded in `web/.shepherd-ui.json`.

### Waveforms (Surfer)

After `shepherd sim`, the UI Artifacts tab embeds **Surfer** for `.vcd` artifact paths (DB stores the path only). VCD bytes are served by `GET /api/artifact?project=…&path=…`. Surfer WASM is fetched into `web/public/surfer/` via `npm run surfer` (also runs on `npm run build` / first `shepherd ui`).
