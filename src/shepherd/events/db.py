"""SQLite events DB: the canonical run store (no run.json)."""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

from shepherd.config import STATE_DIR

DB_NAME = "shepherd.db"
SCHEMA_VERSION = 1

EVENT_KINDS = {"step_start", "step_end", "log", "verdict", "ask", "artifact"}
LEVELS = {"info", "warn", "error"}
VERDICTS = {"pass", "warn", "fail"}


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{secrets.token_hex(2)}"


def _pgid() -> int | None:
    try:
        return os.getpgid(0)
    except (AttributeError, OSError):  # non-POSIX
        return None


class EventStore:
    def __init__(self, conn: sqlite3.Connection, project_root: Path):
        self.conn = conn
        self.project_root = project_root

    @classmethod
    def open(cls, project_root: Path) -> EventStore:
        state = project_root / STATE_DIR
        state.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(state / DB_NAME, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        store = cls(conn, project_root)
        store._migrate()
        return store

    def _migrate(self) -> None:
        (current,) = self.conn.execute("PRAGMA user_version").fetchone()
        if current < 1:
            self.conn.executescript(files("shepherd.events").joinpath("schema.sql").read_text())
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        self.conn.close()

    def start_run(
        self,
        command: str,
        board: str | None = None,
        run_id: str | None = None,
        meta: dict | None = None,
    ) -> Run:
        run = Run(self, run_id or new_run_id())
        self.conn.execute(
            "INSERT INTO runs (id, project_path, command, board, pid, pgid, started_at, meta_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run.id,
                str(self.project_root),
                command,
                board,
                os.getpid(),
                _pgid(),
                now_iso(),
                json.dumps(meta) if meta is not None else None,
            ),
        )
        return run

    def latest_run(self, command: str | None = None) -> sqlite3.Row | None:
        if command:
            return self.conn.execute(
                "SELECT * FROM runs WHERE command = ? ORDER BY started_at DESC, rowid DESC LIMIT 1",
                (command,),
            ).fetchone()
        return self.conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC, rowid DESC LIMIT 1"
        ).fetchone()

    def events(self, run_id: str, after_id: int = 0) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM events WHERE run_id = ? AND id > ? ORDER BY id",
            (run_id, after_id),
        ).fetchall()


@dataclass
class Run:
    store: EventStore
    id: str

    def event(
        self,
        kind: str,
        step: str | None = None,
        level: str = "info",
        message: str | None = None,
        payload: dict | None = None,
    ) -> int:
        if kind not in EVENT_KINDS:
            raise ValueError(f"unknown event kind {kind!r}")
        if level not in LEVELS:
            raise ValueError(f"unknown level {level!r}")
        # Autocommit mode: every row is visible to readers (the UI) immediately.
        cur = self.store.conn.execute(
            "INSERT INTO events (run_id, ts, kind, step, level, message, payload_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self.id,
                now_iso(),
                kind,
                step,
                level,
                message,
                json.dumps(payload) if payload is not None else None,
            ),
        )
        return cur.lastrowid

    def finish(self, verdict: str) -> None:
        if verdict not in VERDICTS:
            raise ValueError(f"unknown verdict {verdict!r}")
        self.store.conn.execute(
            "UPDATE runs SET finished_at = ?, verdict = ? WHERE id = ?",
            (now_iso(), verdict, self.id),
        )
