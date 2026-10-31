-- Shared events DB (contract with the web UI, see PLAN_UI.md).
-- Shepherd (Python) owns writes; the UI only reads.

-- one row per shepherd invocation
CREATE TABLE IF NOT EXISTS runs (
  id            TEXT PRIMARY KEY,
  project_path  TEXT NOT NULL,
  command       TEXT NOT NULL,      -- build | upload | doctor | ...
  board         TEXT,
  pid           INTEGER,            -- OS process id of shepherd (for Cancel)
  pgid          INTEGER,            -- process group id when available
  started_at    TEXT NOT NULL,
  finished_at   TEXT,
  verdict       TEXT,               -- pass | warn | fail | null while running
  meta_json     TEXT
);

-- append-only stream both sides poll
CREATE TABLE IF NOT EXISTS events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id       TEXT NOT NULL REFERENCES runs(id),
  ts           TEXT NOT NULL,
  kind         TEXT NOT NULL,       -- step_start | step_end | log | verdict | ask | artifact
  step         TEXT,                -- adapter | synth | pnr | pack | upload | verify | ...
  level        TEXT,                -- info | warn | error
  message      TEXT,
  payload_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id);
CREATE INDEX IF NOT EXISTS idx_events_id ON events(id);
