"""`shepherd ask` / `shepherd ask wipe`: Q&A and clearing Ask / run history."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import typer

from shepherd import config as config_mod
from shepherd.context import Context
from shepherd.errors import ConfigError, NetworkRequired, ShepherdError
from shepherd.events.db import DB_NAME, EventStore, new_run_id
from shepherd.events.logs import LOCK_NAME, RunDir, RunLock
from shepherd.llm.client import LlmClient, load_config
from shepherd.llm.prompt import build_diagnosis_messages
from shepherd.output import Output, display_path


class AskError(ShepherdError):
    exit_code = 2


def run_ask(ctx: Context, out: Output, question: str) -> int:
    """Answer a project question with optional last-run context via the LLM."""
    if ctx.no_ai:
        raise AskError("AI is disabled (`--no-ai`)", hint="omit `--no-ai` to ask")
    root = config_mod.find_project_root(ctx.project)
    if root is None:
        raise ConfigError(
            f"no {config_mod.CONFIG_NAME} found in {ctx.project} or its parents",
            hint="run `shepherd init` or pass `--project`",
        )
    cfg = config_mod.load(root)
    if not cfg.checks_ai:
        raise AskError(
            "AI is disabled in shepherd.toml ([checks] ai = false)",
            hint="set ai = true under [checks] or omit the section",
        )
    config = load_config(root or ctx.project)
    if not config.enabled:
        raise AskError(
            "META_API_KEY is not set",
            hint="export META_API_KEY or add it to .env (see .env.example)",
        )

    logs: dict[str, str] = {}
    store = EventStore.open(root)
    try:
        # Prefer last build/upload for toolchain logs (skip ask/doctor noise).
        row = store.conn.execute(
            "SELECT * FROM runs WHERE command IN ('build', 'upload') "
            "ORDER BY started_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
        if row is None:
            row = store.latest_run()
        if row is not None:
            run_dir = RunDir(root, row["id"])
            for step in ("adapter", "build", "upload"):
                path = run_dir.log_path(step)
                if path.is_file():
                    logs[step] = path.read_text(errors="replace")

        # Include the latest verify verdict so Ask can explain why Verify failed
        # (verify runs have no step logs of their own).
        verify_row = store.conn.execute(
            "SELECT * FROM runs WHERE command = 'verify' "
            "ORDER BY started_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
        if verify_row is not None:
            lines = [f"verify run {verify_row['id']}: verdict={verify_row['verdict'] or 'unknown'}"]
            for ev in store.conn.execute(
                "SELECT kind, level, message, payload_json FROM events "
                "WHERE run_id = ? AND step = 'verify' "
                "ORDER BY id ASC",
                (verify_row["id"],),
            ):
                if ev["message"]:
                    lines.append(f"[{ev['kind']}] {ev['message']}")
                if ev["payload_json"]:
                    try:
                        payload = json.loads(ev["payload_json"])
                        for f in payload.get("findings") or []:
                            if f.get("cause"):
                                lines.append(f"cause: {f['cause']}")
                            if f.get("fix"):
                                lines.append(f"fix: {f['fix']}")
                    except (TypeError, ValueError):
                        pass
            logs["verify"] = "\n".join(lines)

        # Dedicated run so UI --run-id polling sees the answer on *this* invocation.
        run = store.start_run(
            "ask",
            board=cfg.board,
            run_id=ctx.run_id or new_run_id(),
            meta={"question": question},
        )
        run.event("step_start", step="ask", message=question)
        try:
            messages = build_diagnosis_messages(cfg=cfg, logs=logs, step=None, question=question)
            result = LlmClient(config).chat(messages)
        except NetworkRequired:
            run.event(
                "step_end",
                step="ask",
                level="error",
                message="network required",
                payload={"ok": False},
            )
            run.finish("fail")
            raise
        except Exception as e:
            run.event(
                "step_end",
                step="ask",
                level="error",
                message=str(e),
                payload={"ok": False},
            )
            run.finish("fail")
            raise

        answer = result.text.strip()
        out.headline("ask")
        out.detail(answer)
        run.event(
            "ask",
            step="ask",
            message=question,
            payload={"answer": answer, "question": question},
        )
        run.event("step_end", step="ask", level="info", message="ok", payload={"ok": True})
        run.event("verdict", step="ask", message="pass", payload={"answer": answer})
        run.finish("pass")
        return 0
    finally:
        store.close()


def _state_dir(root: Path) -> Path:
    return root / config_mod.STATE_DIR


def _db_paths(state: Path) -> list[Path]:
    return [state / DB_NAME, state / f"{DB_NAME}-wal", state / f"{DB_NAME}-shm"]


def _count_runs(db_path: Path) -> int:
    if not db_path.is_file():
        return 0
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("SELECT COUNT(*) FROM runs").fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


def run_ask_wipe(ctx: Context, out: Output) -> int:
    """Wipe Ask / run history under `.shepherd` (keep build artifacts)."""
    root = config_mod.find_project_root(ctx.project)
    if root is None:
        raise ConfigError(
            f"no {config_mod.CONFIG_NAME} found in {ctx.project} or its parents",
            hint="run `shepherd init` or pass `--project`",
        )

    state = _state_dir(root)
    db_path = state / DB_NAME
    runs_dir = state / "runs"
    lock_path = state / LOCK_NAME
    n_runs = _count_runs(db_path)
    has_runs_dir = runs_dir.is_dir()
    has_db = any(p.exists() for p in _db_paths(state))
    has_lock = lock_path.exists()

    board = None
    try:
        board = config_mod.load(root).board
    except Exception:
        board = None

    if not has_db and not has_runs_dir and not has_lock:
        out.headline("ask wipe")
        out.detail("nothing to wipe")
        _record_wipe_run(ctx, root, board=board, cleared=0, dry_run=ctx.dry_run)
        return 0

    out.headline("ask wipe")
    out.detail(f"project: {display_path(root)}")
    if has_db:
        out.detail(f"runs in db: {n_runs}")
    if has_runs_dir:
        out.detail(f"remove: {display_path(runs_dir)}/")
    for p in _db_paths(state):
        if p.exists():
            out.detail(f"remove: {display_path(p)}")
    if has_lock:
        out.detail(f"remove: {display_path(lock_path)}")
    out.detail("keep: .shepherd/build/, .shepherd/gen/")

    if ctx.dry_run:
        out.detail("dry run: nothing deleted")
        return 0

    if not ctx.yes and not typer.confirm("Wipe Ask / run history for this project?", default=False):
        raise AskError("ask wipe cancelled", hint="re-run with `--yes` to skip the prompt")

    run_id = ctx.run_id or new_run_id()
    with RunLock(root, run_id):
        if runs_dir.is_dir():
            shutil.rmtree(runs_dir)
        for p in _db_paths(state):
            p.unlink(missing_ok=True)

    _record_wipe_run(ctx, root, board=board, cleared=n_runs, dry_run=False, run_id=run_id)
    out.detail(f"wiped {n_runs} run(s); Ask / explain / verify history is empty")
    return 0


def _record_wipe_run(
    ctx: Context,
    root: Path,
    *,
    board: str | None,
    cleared: int,
    dry_run: bool,
    run_id: str | None = None,
) -> None:
    """Write a finished `wipe` run so the UI poller sees finished_at after wipe."""
    if dry_run or ctx.dry_run:
        return
    rid = run_id or ctx.run_id or new_run_id()
    store = EventStore.open(root)
    try:
        run = store.start_run("wipe", board=board, run_id=rid)
        run.event("step_start", step="wipe")
        run.event(
            "log",
            step="wipe",
            message=f"wiped {cleared} run(s); build artifacts kept",
        )
        run.event(
            "step_end",
            step="wipe",
            level="info",
            payload={"ok": True, "cleared": cleared},
        )
        run.event("verdict", step="wipe", message="pass", payload={"cleared": cleared})
        run.finish("pass")
    finally:
        store.close()
