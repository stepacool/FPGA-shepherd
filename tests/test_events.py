from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from shepherd.errors import RunLocked
from shepherd.events.db import EventStore
from shepherd.events.logs import RunDir, RunLock


def test_schema_and_wal(tmp_path: Path):
    store = EventStore.open(tmp_path)
    (mode,) = store.conn.execute("PRAGMA journal_mode").fetchone()
    assert mode == "wal"
    tables = {r[0] for r in store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"runs", "events"} <= tables
    store.close()
    # Re-opening does not re-run the migration.
    EventStore.open(tmp_path).close()


def test_run_lifecycle(tmp_path: Path):
    store = EventStore.open(tmp_path)
    run = store.start_run("build", board="tangnano9k", run_id="r1")
    first = run.event("step_start", step="synth")
    run.event("log", step="synth", level="warn", message="Warning: x")
    run.event("step_end", step="synth", payload={"ok": True})
    run.finish("pass")

    row = store.latest_run()
    assert row["id"] == "r1"
    assert row["verdict"] == "pass"
    assert row["finished_at"] is not None
    assert row["pid"] == os.getpid()

    events = store.events("r1")
    assert [e["kind"] for e in events] == ["step_start", "log", "step_end"]
    assert json.loads(events[2]["payload_json"]) == {"ok": True}
    assert [e["kind"] for e in store.events("r1", after_id=first)] == ["log", "step_end"]


def test_latest_run_by_command(tmp_path: Path):
    store = EventStore.open(tmp_path)
    store.start_run("build", run_id="a")
    store.start_run("upload", run_id="b")
    assert store.latest_run()["id"] == "b"
    assert store.latest_run("build")["id"] == "a"


@pytest.mark.parametrize(
    ("call", "args"),
    [("event", {"kind": "bogus"}), ("event", {"kind": "log", "level": "fatal"})],
)
def test_invalid_event_rejected(tmp_path: Path, call, args):
    run = EventStore.open(tmp_path).start_run("build")
    with pytest.raises(ValueError):
        getattr(run, call)(**args)


def test_invalid_verdict_rejected(tmp_path: Path):
    run = EventStore.open(tmp_path).start_run("build")
    with pytest.raises(ValueError):
        run.finish("maybe")


def test_reader_sees_events_while_writing(tmp_path: Path):
    run = EventStore.open(tmp_path).start_run("build", run_id="live")
    run.event("step_start", step="synth")
    reader = sqlite3.connect(tmp_path / ".shepherd" / "shepherd.db")
    (count,) = reader.execute("SELECT COUNT(*) FROM events WHERE run_id='live'").fetchone()
    assert count == 1
    run.event("step_end", step="synth")
    (count,) = reader.execute("SELECT COUNT(*) FROM events WHERE run_id='live'").fetchone()
    assert count == 2


def test_run_dir_and_pid(tmp_path: Path):
    run_dir = RunDir(tmp_path, "r1")
    assert run_dir.log_path("build") == tmp_path / ".shepherd/runs/r1/build.log"
    run_dir.write_pid()
    pid_file = run_dir.path / "pid"
    assert pid_file.read_text().split()[0] == str(os.getpid())
    run_dir.remove_pid()
    assert not pid_file.exists()


def test_lock_refuses_second_run(tmp_path: Path):
    with RunLock(tmp_path, "r1"), pytest.raises(RunLocked, match="r1"):
        RunLock(tmp_path, "r2").acquire()
    # Released on exit.
    with RunLock(tmp_path, "r3"):
        pass


def test_stale_lock_reclaimed(tmp_path: Path):
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    lock_path = tmp_path / ".shepherd" / "lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(f"{dead.pid} old\n")
    with pytest.warns(UserWarning, match="stale"), RunLock(tmp_path, "new"):
        assert lock_path.read_text().split()[1] == "new"
