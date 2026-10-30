# FPGA Shepherd — UI plan

Companion to [`PLAN.md`](PLAN.md). This document covers the optional **web user interface (UI)**, the endpoints the Shepherd **command-line interface (CLI)** uses, the Python job processor, and how we host them on free tiers.

## Goal

A light **Next.js** app that shows Shepherd runs live: steps, verdicts, logs, ask/explain, and (later) waveforms. The same app serves the endpoints the CLI calls. The real work (builds, uploads, adapters, AI diagnosis) is done by Python **job processors**.

**Core rule: the database (DB) is the wire.** Two services, one Postgres, no direct calls between them:

| Service | What it is | Talks to |
| --- | --- | --- |
| **Next.js** (Vercel or `localhost:3000`) | UI pages + **application programming interface (API)** endpoints for the CLI | Postgres (read events/results, write jobs) |
| **`shepherd worker`** (Python, laptop with the board) | Job processor: claims jobs, runs Shepherd, writes events/results | Postgres (read jobs, write events/results) |

- Postgres is addressed by a connection **URI** (`DATABASE_URL`): local Postgres or Neon, same code
- Next.js never calls the worker; the worker never calls Next.js. No FastAPI, no Python HTTP server, no tunnel
- The CLI and the browser are both clients of Next.js

## Acronyms

Same glossary as [`PLAN.md`](PLAN.md). Extra for this file:

| Acronym | Meaning |
| --- | --- |
| **CU** | compute unit (Neon’s compute size; 0.25 CU is the smallest) |
| **SSE** | server-sent events (not used in v0) |
| **URI** | uniform resource identifier (here: a `postgres://…` connection string) |
| **URL** | uniform resource locator (here: the Next.js app address, e.g. `https://….vercel.app`) |
| **VCD** | value change dump (simulation waveform file) |
| **WASM** | WebAssembly |

## Architecture

```mermaid
flowchart LR
  BROWSER[Browser]
  CLI[shepherd_CLI]
  subgraph Next[Next_js_on_Vercel_or_localhost]
    UI[UI_pages]
    API[api_routes_for_CLI]
  end
  DB[(Postgres_Neon_or_local)]
  subgraph Laptop[Laptop_with_board]
    WORKER[shepherd_worker_job_processor]
    BOARD[Tang_Nano_9K]
  end
  BROWSER --> UI
  CLI -->|HTTPS| API
  UI -->|insert_jobs_read_events| DB
  API -->|insert_jobs_read_events| DB
  WORKER -->|claim_jobs_write_events_and_results| DB
  WORKER -->|USB| BOARD
```

Flow of one `shepherd build` (or a Build button click):

1. CLI `POST /api/jobs` (or a UI Server Action) → Next.js inserts a `jobs` row (`status = queued`) and `NOTIFY`s
2. The worker hears the notification, claims the row (`FOR UPDATE SKIP LOCKED`), runs the build in-process
3. The worker appends `events` rows as steps progress, then writes the verdict/result to the `jobs` row (`status = done`)
4. CLI (or UI) polls Next.js for new events by cursor and prints/renders them until the job is finished

### Two CLI modes

| Mode | When | What happens |
| --- | --- | --- |
| **Local** (default) | `SHEPHERD_SERVER_URL` unset, or `--local` | Command runs in-process exactly as in [`PLAN.md`](PLAN.md); `.shepherd/runs/` files only; no server, no DB |
| **Server** | `SHEPHERD_SERVER_URL` set | Command becomes a job via Next.js; output streams back from the DB; shows up in the UI |

Both modes run the same job code (`src/shepherd/jobs/`). The worker is just that code driven by the `jobs` table instead of by argv.

Interactive commands (`doctor --fix` with confirmations, `init`) stay **local-only** in v0. `shepherd doctor` on a fresh machine must not depend on a server.

**v0 limitation:** the worker runs jobs on project directories **it has locally** (it registers them; jobs reference a project id). In practice the CLI is used on the board laptop, or teammates queue jobs for projects that are checked out there. Shipping sources with the job (git ref or uploaded bundle) is later work.

## Hosting setup (free tiers)

| Piece | Where | Cost | Why this one |
| --- | --- | --- | --- |
| **Next.js** (UI + CLI endpoints) | **Vercel Hobby** | $0 | First-party Next.js host; git push → deploy; preview URLs per PR |
| **DB** (Postgres, the wire) | **Neon Free** | $0 | Plain Postgres behind a URI; scales to zero instead of pausing; one-click Vercel integration |
| **Job processor** (`shepherd worker`) | **One of our laptops** (the one with the Tang Nano 9K plugged in) | $0 | Needs the toolchain and the board over **USB**, so it can’t run on a serverless host anyway |

So the hosted stack is just **Vercel + Neon**, plus a laptop we already own.

### Free-tier limits that matter to us (checked Oct 2026)

| Service | Limit | What it means for Shepherd |
| --- | --- | --- |
| Vercel Hobby | Non-commercial / personal use only | Fine for hackathon + team use; move to **Vercel Pro** if this becomes a product |
| Vercel Hobby | Function max duration 300 s | Endpoints are short reads/inserts; jobs run on the laptop, not in functions |
| Vercel Hobby | Monthly quotas on function invocations / active CPU; exceeding one **pauses** it (no surprise bill) | Only CLI and browser polling hit Vercel; the worker talks to Neon directly |
| Neon Free | 0.5 GB storage per project | Store log **tails** and structured events; full logs stay in `.shepherd/runs/` on the laptop |
| Neon Free | 100 CU-hours per project per month (compute suspends when used up) | ~400 awake hours/month at 0.25 CU. An open worker connection keeps Neon awake (see Budget) |
| Neon Free | Scales to zero after ~5 min with no connections; wakes on next connection (sub-second cold start) | No manual “restore project” step, unlike Supabase Free |
| Neon Free | 5 GB egress per month | Plenty for event rows |

Numbers move; re-check [neon.com/pricing](https://neon.com/pricing) and [vercel.com/docs/plans/hobby-plan](https://vercel.com/docs/plans/hobby-plan) before relying on them.

### Why Neon over Supabase (and the others)

- **Supabase Free** is also just Postgres behind a URI and would work with zero code changes. But free projects **pause after 7 days of inactivity** and must be restored from the dashboard. That’s bad for a project we touch in bursts. Its extras (auth, realtime, storage) aren’t needed for v0.
- **Neon** suspends compute instead of pausing the project, so the first query after a quiet week just works. The Vercel marketplace integration injects `DATABASE_URL` (pooled) and `DATABASE_URL_UNPOOLED` (direct) into the Vercel project.
- **Vercel’s own “Postgres”** is Neon under the hood now. Use Neon directly so the DB isn’t tied to a Vercel project (deleting a Vercel-managed integration deletes the DB).

**Rule:** both services code only against standard Postgres: `postgres.js` in Next.js, `psycopg` (v3) in Python. No Neon or Supabase client libraries, so any provider (or `localhost`) is just a URI change.

## Local mode vs hosted mode

Same code, different addresses:

| | Local (dev) | Hosted (demo / team) |
| --- | --- | --- |
| Postgres | `docker run -p 5432:5432 -e POSTGRES_PASSWORD=dev postgres:17` (or Postgres.app) | Neon project, `main` branch |
| `DATABASE_URL` (Next.js) | `postgres://postgres:dev@localhost:5432/postgres` | Neon **pooled** URI (serverless functions open many short connections) |
| `DATABASE_URL` (worker) | same as above | Neon **direct** URI (long-lived connection; `LISTEN` needs it) |
| Next.js | `pnpm dev` in `web/` → `http://localhost:3000` | Vercel deployment |
| `SHEPHERD_SERVER_URL` (CLI) | `http://localhost:3000` | `https://<project>.vercel.app` |
| Worker | `uv run shepherd worker` | `uv run shepherd worker` on the board laptop |

Mixes work too, e.g. local `pnpm dev` against the shared Neon URI to develop UI with real jobs.

Neon branches: optionally one `dev-<name>` branch per teammate for schema experiments. **Don’t** turn on per-preview-deployment DB branches. The worker listens on one branch, so previews should read `main`.

## DB schema (the wire)

The schema is the contract between the two services. It lives in a neutral place, `db/migrations/*.sql` at the repo root, applied by one tool: `pnpm db:migrate` in `web/` (a ~30-line `postgres.js` script, run against the direct URI). Neither service migrates on startup. Types are mirrored by hand in `web/src/lib/types.ts` and `src/shepherd/jobs/model.py`.

```sql
-- one row per laptop running `shepherd worker`
CREATE TABLE workers (
  id            TEXT PRIMARY KEY,          -- stable id from ~/.config/shepherd/worker_id
  name          TEXT NOT NULL,             -- e.g. "stepan-mbp"
  projects      JSONB NOT NULL,            -- [{ "id": "...", "name": "...", "board": "tang_nano_9k" }]
  last_seen_at  TIMESTAMPTZ NOT NULL       -- heartbeat; UI/CLI show worker online/offline
);

-- one row per Shepherd command run in server mode: request + status + result
CREATE TABLE jobs (
  id            BIGSERIAL PRIMARY KEY,
  worker_id     TEXT NOT NULL REFERENCES workers(id),
  project_id    TEXT NOT NULL,             -- must be one the worker advertised
  command       TEXT NOT NULL,             -- allowlisted: build | upload | lint | sim | test | report | explain | ask
  args          JSONB NOT NULL DEFAULT '{}', -- validated flags, e.g. { "flash": true } or { "question": "…" }; never raw shell
  source        TEXT NOT NULL,             -- cli | ui
  status        TEXT NOT NULL DEFAULT 'queued', -- queued | running | done | failed | rejected | cancelled
  verdict       TEXT,                      -- pass | warn | fail
  result        JSONB,                     -- summary, next steps, artifact list (what `--json` prints)
  error         TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at    TIMESTAMPTZ,
  finished_at   TIMESTAMPTZ
);
CREATE INDEX idx_jobs_queued ON jobs(worker_id, id) WHERE status = 'queued';

-- append-only stream; worker writes, Next.js reads
CREATE TABLE events (
  id         BIGSERIAL PRIMARY KEY,
  job_id     BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
  kind       TEXT NOT NULL,                -- step_start | step_end | log | verdict | ask | artifact
  step       TEXT,                         -- synth | pnr | upload | verify | …
  level      TEXT,                         -- info | warn | error
  message    TEXT,
  payload    JSONB
);
CREATE INDEX idx_events_job_id_id ON events(job_id, id);
```

**Ownership per column**, so the two services never fight:

| Who | Writes |
| --- | --- |
| Next.js | `jobs` inserts (`status = queued`); `status = cancelled` while still queued |
| Worker | `workers` upsert/heartbeat; everything on `jobs` after claim (`status`, `verdict`, `result`, `error`, timestamps); all `events` |

**Wake-up:** Next.js runs `SELECT pg_notify('jobs', worker_id)` after inserting. The worker holds `LISTEN jobs` on its direct connection and also re-checks the queue every 30 s in case a notification was missed.

**Storage hygiene (0.5 GB budget):** `log` events carry at most the last ~200 lines per step; the full log path goes in an `artifact` event. The worker deletes jobs older than 30 days on startup (`ON DELETE CASCADE` cleans events).

## `shepherd worker` (job processor)

New CLI command in `src/shepherd/worker.py`:

1. Require `DATABASE_URL`. Upsert its `workers` row with the projects it serves (`--project PATH` flags or a `[worker]` list in config). Project ids come from `shepherd.toml`. **Paths never leave the laptop**: the DB only has ids and names.
2. `LISTEN jobs`. On notify (or every 30 s), claim the oldest queued job for this worker:
   `UPDATE jobs SET status='running', started_at=now() WHERE id = (SELECT id FROM jobs WHERE worker_id=$1 AND status='queued' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *`
3. Validate: command in allowlist, project id known, args match the command’s schema. Otherwise `status = rejected`.
4. Run the command **in-process** through `src/shepherd/jobs/` (same code as local mode, not a shell string). Events are buffered and inserted in small batches (~every 500 ms and at step boundaries). `.shepherd/runs/` files are still written.
5. Write `verdict`, `result`, `finished_at`, `status = done | failed`.
6. Heartbeat `last_seen_at` every ~15 s. One job at a time, since there’s one board.
7. **Exit after 30 min with no jobs** (`--idle-exit`, default `30m`, `0` = never). See Budget.

## Next.js API (for the CLI)

Route Handlers under `web/src/app/api/`. JSON in/out, `zod`-validated, `Authorization: Bearer $SHEPHERD_API_TOKEN`. Each one is a short DB read or insert; none of them does any job work.

| Method + path | Does |
| --- | --- |
| `GET /api/workers` | Online workers and the projects they serve (CLI uses it to pick a worker for the current project) |
| `POST /api/jobs` | `{ project_id, command, args }` → insert `queued` job + notify; returns `{ job_id }`. `409` if no online worker serves the project |
| `GET /api/jobs/:id` | Status, verdict, result |
| `GET /api/jobs/:id/events?after=<event_id>&wait=20` | Events after the cursor; **long-polls** up to `wait` seconds if none yet. Also returns job status so the CLI knows when to stop |
| `POST /api/jobs/:id/cancel` | Cancel while still queued |

The CLI client is `src/shepherd/server_client.py` (`httpx`, already a dependency of the LLM client). In server mode, `shepherd build` = `POST /api/jobs` → loop on `/events` printing as it goes → exit code from the verdict. `--json` prints `result` like local mode does.

The UI uses Server Components / Server Actions against the DB directly, plus the same `/events` route for live polling (browser auth via the UI password instead of the bearer token).

## Budget (free-tier usage)

- **Neon compute:** Neon suspends only when no connections are open, so a running worker keeps it awake. 100 CU-hours at 0.25 CU ≈ 400 awake hours/month ≈ 13 h/day. A worker left on 24/7 (~180 CU-hours) would hit the cap mid-month. Hence `--idle-exit`: start the worker when working or demoing; it stops itself.
- **Vercel invocations:** the worker doesn’t touch Vercel. CLI and UI use long-poll `/events?wait=20`, so a streaming job costs a few calls per minute, not one per second. The UI polls only while the tab is visible and a job is active; runs list / worker status every ~10 s.
- **Neon storage:** log tails + 30-day retention (above).
- If we ever need more: Vercel Pro and Neon Launch (usage-based), or Supabase Pro as a URI change.

## Access control (hosted)

A public URL that can make a laptop flash an FPGA needs a lock, even for a demo:

- **Browser:** Next.js middleware with HTTP basic auth against `SHEPHERD_UI_PASSWORD`. Shared team password, no user accounts.
- **CLI:** `Authorization: Bearer $SHEPHERD_API_TOKEN` on `/api/*`. One shared token for v0 (`openssl rand -hex 32`).
- **Worker:** holds `DATABASE_URL` (direct). Only the board laptop needs it. Teammates using just the CLI need only the server URL + token.
- The worker trusts nothing in a job beyond an allowlisted command, a known project id, and schema-checked args. No paths, no shell, no free-form backend args.
- Per-user auth / per-worker credentials are out of scope for v0.

## Next.js app

**Location:** `web/` at the repo root; Vercel project root directory = `web`.

| Piece | Choice | Why |
| --- | --- | --- |
| App | Next.js (App Router) | UI + CLI endpoints in one deployable; native on Vercel |
| Language | TypeScript | Safer for a team hackathon |
| Styling | One small system (e.g. CSS modules or Tailwind) | Don’t over-design |
| DB access | **`postgres`** (postgres.js) via `DATABASE_URL`, server-side only | Standard Postgres driver: works with localhost, Neon, Supabase |
| Validation | `zod` on every Route Handler body | The CLI is an external client; validate like one |
| Live updates | Long-poll `/api/jobs/:id/events` | Demo-simple; no WebSockets |
| Charts / scope | See Waveforms below | Don’t pull heavy dashboards |

**Pages / areas (v0):**

1. **Workers**: which laptops are online (`last_seen_at`), which projects/boards they serve
2. **Project**: board, top, last verdict, buttons to queue build / upload
3. **Job**: live event feed (steps + log lines + verdict); CLI-started and UI-started jobs look the same
4. **Explain / Ask**: show AI findings from events; queue `explain` / `ask`
5. **Artifacts**: artifact names and sizes from `payload` (files stay on the laptop in v0)

Advanced “show backend” can be a toggle that reveals `backend_cmd` fields from payloads. Shepherd terms stay the default.

Do **not** reimplement build in Node. Do **not** call apio from Next.js. Do **not** spawn processes from Next.js.

## Environment variables

| Variable | Where | Value |
| --- | --- | --- |
| `DATABASE_URL` | Vercel env / `web/.env.local` | Neon pooled URI, or local Postgres URI |
| `DATABASE_URL_UNPOOLED` | Vercel env / `web/.env.local` | Neon direct URI (migrations); same as above locally |
| `DATABASE_URL` | board laptop `.env` (worker) | Neon direct URI, or local Postgres URI |
| `SHEPHERD_UI_PASSWORD` | Vercel env / `web/.env.local` | shared team password |
| `SHEPHERD_API_TOKEN` | Vercel env **and** CLI `.env` | shared bearer token |
| `SHEPHERD_SERVER_URL` | CLI `.env` | `http://localhost:3000` or the Vercel URL; unset = local mode |

Add the Python-side variables (empty) to `.env.example` and a `web/.env.example` for the rest. Never commit real values.

## Waveforms (“oscilloscope”)

Phased so the demo stays light:

| Phase | Need | Approach |
| --- | --- | --- |
| **v0** | Live job UX | Event feed only, no scope |
| **v0.5** | Sim waveforms | Locally: open **Surfer** (**WASM**) on the **VCD**/FST path from the `artifact` event. Hosted: the worker uploads small VCDs to object storage (e.g. Vercel Blob free tier) and puts the URL in the artifact payload |
| **later** | Live UART samples | Worker writes sample events (or a side table); UI plots with **uPlot** or canvas |

Do not adopt heavy instrumentation frameworks for the hackathon.

## Repo layout (UI-related)

```text
PLAN.md
PLAN_UI.md                  # this file
.env.example                # + DATABASE_URL (worker), SHEPHERD_SERVER_URL, SHEPHERD_API_TOKEN
db/
  migrations/*.sql          # the wire: shared schema, applied by `pnpm db:migrate`
web/                        # Next.js: UI + CLI endpoints (Vercel root directory)
  package.json
  .env.example
  middleware.ts             # basic auth for pages; bearer check for /api
  scripts/migrate.ts        # applies ../db/migrations
  src/app/(ui)/...          # pages
  src/app/api/...           # workers, jobs, events Route Handlers
  src/lib/db.ts             # postgres.js client
  src/lib/types.ts          # job / event shapes (mirror of Python model)
src/shepherd/
  jobs/                     # command implementations shared by local mode and the worker
    model.py                # job / event dataclasses (mirror of web types)
  server_client.py          # CLI server mode: httpx client for /api/*
  worker.py                 # `shepherd worker`: LISTEN, claim, run, write events/results
  db.py                     # psycopg connection + queries used by the worker
  ...
```

## What stays in PLAN.md vs here

| Concern | Document |
| --- | --- |
| CLI commands, apio backend, agents, adapters, Tang Nano 9K | [`PLAN.md`](PLAN.md) |
| Next.js pages + CLI endpoints, DB schema, worker, hosting, budget, Surfer/uPlot | **this file** |
| Shared decision: **Postgres is the wire between Next.js and the Python worker; no direct calls, no FastAPI** | both (brief in PLAN.md, detail here) |

## Out of scope for UI v0

- Any direct call between Next.js and Python (FastAPI, Express, Python HTTP server, webhooks)
- Inbound tunnels to the laptop (ngrok, Cloudflare Tunnel)
- Running jobs in the cloud (no board there)
- Shipping project sources with a job (worker uses its local checkouts)
- Interactive commands (`doctor --fix`, `init`) in server mode
- WebSockets / SSE (long-poll is enough)
- Electron / Tauri packaging
- Per-user auth / multi-tenant hosting
- Provider-specific SDKs (Neon serverless driver, Supabase client): plain Postgres only
- Replacing Surfer with a custom full waveform engine
- Driving apio or openFPGALoader from Node

## Implementation order (UI)

1. Agree `db/migrations/001_init.sql` and the `types.ts` ↔ `model.py` shapes
2. Refactor command bodies into `src/shepherd/jobs/` so local mode and the worker share them
3. `shepherd worker` against local Docker Postgres: insert a job by hand with `psql`, watch events appear
4. Scaffold `web/`: `db.ts`, migrate script, `/api/jobs` + `/events`; Job page with live feed
5. CLI server mode (`server_client.py`): `shepherd build` with `SHEPHERD_SERVER_URL=http://localhost:3000`
6. UI buttons (Server Actions) + Workers page
7. Create Neon project + Vercel project (root `web/`), set env vars, middleware auth; point the board laptop’s worker at Neon and the CLI at the Vercel URL
8. Explain/Ask surfaces
9. Optional: Surfer for sim artifacts

## Success criteria (UI)

- `shepherd build` in server mode and the Build button produce the same job; both stream the same events from the DB
- A teammate on another machine opens the Vercel URL (or uses the CLI with the token) and watches/queues jobs on the board laptop
- Next.js and the worker never call each other; killing either one leaves the other healthy and the DB consistent (queued jobs wait, finished jobs stay readable)
- Switching DB (local ↔ Neon) is a `DATABASE_URL` change; switching server (local ↔ Vercel) is a `SHEPHERD_SERVER_URL` change
- Monthly cost: $0 (Vercel Hobby + Neon Free + our laptop)
- Local mode works with no server or DB at all, including `doctor` on a fresh machine
- Judges can follow synth → P&R → verdict without reading raw apio commands
- Adding waveform view later does not require changing the event shape (artifact events already exist)
