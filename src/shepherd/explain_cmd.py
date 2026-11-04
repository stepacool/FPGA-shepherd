"""`shepherd explain` and `shepherd check`: VerifyAgent on a log or last run."""

from __future__ import annotations

from pathlib import Path

from shepherd import config as config_mod
from shepherd.agents.verify import VerifyAgent
from shepherd.checks.checkpoints import CheckContext, Finding
from shepherd.checks.checkpoints import check as run_checkpoint
from shepherd.context import Context
from shepherd.errors import ConfigError, ShepherdError
from shepherd.events.db import EventStore
from shepherd.events.logs import RunDir
from shepherd.output import Output, display_path


class ExplainError(ShepherdError):
    exit_code = 2


def _load_cfg(ctx: Context):
    root = config_mod.find_project_root(ctx.project)
    if root is None:
        return None, None
    return root, config_mod.load(root)


def _print_verdict(out: Output, findings: list[Finding], log_hint: str | None) -> None:
    if not findings:
        out.verdict("pass")
        out.detail("no known error signatures matched")
        if log_hint:
            out.detail(f"log:   {log_hint}")
        return
    level = "fail" if any(f.level == "error" for f in findings) else "warn"
    out.verdict(level)
    for f in findings:
        if f.cause:
            out.detail(f"cause: {f.cause}")
        elif f.message:
            out.detail(f"error: {f.message}", "red")
        if f.fix:
            out.detail(f"fix:   {f.fix}")
    if log_hint:
        out.detail(f"log:   {log_hint}   (or re-run with -v)")


def _step_logs(root, run_id: str) -> dict[str, str]:
    run_dir = RunDir(root, run_id)
    logs: dict[str, str] = {}
    for step in ("adapter", "build", "upload"):
        path = run_dir.log_path(step)
        if path.is_file():
            logs[step] = path.read_text(errors="replace")
    return logs


def _pick_explain_row(store: EventStore):
    """Prefer a failed build/upload with logs; else any run that has step logs."""
    candidates = store.conn.execute(
        "SELECT * FROM runs WHERE command IN ('build', 'upload') "
        "ORDER BY CASE verdict WHEN 'fail' THEN 0 ELSE 1 END, "
        "started_at DESC, rowid DESC"
    ).fetchall()
    for row in candidates:
        if _step_logs(store.project_root, row["id"]):
            return row
    # Last resort: scan recent runs (skip ask/wipe/explain noise when possible).
    for row in store.conn.execute(
        "SELECT * FROM runs ORDER BY started_at DESC, rowid DESC LIMIT 20"
    ):
        if row["command"] in ("ask", "wipe", "explain", "doctor", "verify", "reset"):
            continue
        if _step_logs(store.project_root, row["id"]):
            return row
    return store.latest_run()


def run_explain(ctx: Context, out: Output, log: Path | None) -> int:
    """Diagnose a log file or the latest failed run; return process exit code."""
    agent = VerifyAgent()
    root = None
    board = None
    try:
        if log is not None:
            path = log.expanduser().resolve()
            if not path.is_file():
                raise ExplainError(f"log file not found: {path}")
            text = path.read_text(errors="replace")
            root, cfg = _load_cfg(ctx)
            board = cfg.board if cfg else None
            verdict = agent.explain_text(text, cfg=cfg)
            _print_verdict(out, verdict.findings, display_path(path))
            if root is not None and not ctx.dry_run:
                _record_explain_run(ctx, root, board, verdict)
            return 0 if verdict.level == "pass" else 1

        root, cfg = _load_cfg(ctx)
        board = cfg.board if cfg else None
        if root is None:
            raise ExplainError(
                "no shepherd.toml found and no log path given",
                hint="pass a log file: `shepherd explain path/to.log`",
            )
        store = EventStore.open(root)
        try:
            row = _pick_explain_row(store)
            if row is None:
                raise ExplainError("no runs recorded yet", hint="run `shepherd build` first")
            logs = _step_logs(root, row["id"])
            if not logs:
                raise ExplainError(
                    f"no step logs for run {row['id']}",
                    hint="run `shepherd build` (or upload) once, then explain again",
                )
            verdict = agent.run(cfg=cfg, logs=logs, allow_ai=False)
            hint = display_path(
                RunDir(root, row["id"]).log_path("build" if "build" in logs else next(iter(logs)))
            )
            _print_verdict(out, verdict.findings, hint)
            _record_explain_run(ctx, root, board, verdict, store=store)
            return 0 if verdict.level == "pass" else 1
        finally:
            store.close()
    except ShepherdError as e:
        # Always finish the UI-allocated run_id so the control room leaves "Explaining…".
        if root is not None and ctx.run_id and not ctx.dry_run:
            _record_explain_error(ctx, root, board, e.message)
        raise


def _record_explain_error(ctx: Context, root, board: str | None, message: str) -> None:
    from shepherd.events.db import new_run_id

    store = EventStore.open(root)
    try:
        run = store.start_run(
            "explain",
            board=board,
            run_id=ctx.run_id or new_run_id(),
        )
        run.event("step_start", step="explain")
        run.event("log", step="explain", level="error", message=message)
        run.event(
            "verdict",
            step="explain",
            level="error",
            message="fail",
            payload={"error": message},
        )
        run.event("step_end", step="explain", level="error", payload={"ok": False})
        run.finish("fail")
    finally:
        store.close()


def _record_explain_run(ctx, root, board, verdict, store: EventStore | None = None) -> None:
    """Write explain findings under ctx.run_id so the UI poller can display them."""
    from shepherd.events.db import new_run_id

    if ctx.dry_run:
        return
    own = store is None
    if store is None:
        store = EventStore.open(root)
    try:
        run = store.start_run(
            "explain",
            board=board,
            run_id=ctx.run_id or new_run_id(),
        )
        run.event("step_start", step="explain")
        payload = {
            "findings": [
                {
                    "id": f.id,
                    "level": f.level,
                    "message": f.message,
                    "cause": f.cause,
                    "fix": f.fix,
                }
                for f in verdict.findings
            ]
        }
        run.event(
            "verdict",
            step="explain",
            level="error" if verdict.level == "fail" else "info",
            message=verdict.level,
            payload=payload,
        )
        for f in verdict.findings:
            if f.cause:
                run.event("log", step="explain", level=f.level, message=f"cause: {f.cause}")
            if f.fix:
                run.event("log", step="explain", level="info", message=f"fix:   {f.fix}")
        run.event(
            "step_end",
            step="explain",
            level="error" if verdict.level == "fail" else "info",
            payload={"ok": verdict.level != "fail"},
        )
        run.finish("fail" if verdict.level == "fail" else "pass")
    finally:
        if own:
            store.close()


def run_verify(ctx: Context, out: Output) -> int:
    """Run VerifyAgent on the latest run's logs; record a `verify` step for the UI."""
    root, cfg = _load_cfg(ctx)
    if root is None or cfg is None:
        raise ConfigError(
            f"no {config_mod.CONFIG_NAME} found in {ctx.project} or its parents",
            hint="run `shepherd init` or pass `--project`",
        )
    store = EventStore.open(root)
    try:
        # Prefer the latest successful upload; fall back to latest run with logs.
        row = store.conn.execute(
            "SELECT * FROM runs WHERE command = 'upload' AND verdict = 'pass' "
            "ORDER BY started_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
        if row is None:
            row = store.latest_run()
        if row is None:
            raise ExplainError("no runs recorded yet", hint="run `shepherd upload` first")
        run_dir = RunDir(root, row["id"])
        logs: dict[str, str] = {}
        for step in ("adapter", "build", "upload"):
            path = run_dir.log_path(step)
            if path.is_file():
                logs[step] = path.read_text(errors="replace")
        if not logs:
            raise ExplainError(
                f"no step logs for run {row['id']}",
                hint="run `shepherd upload` first",
            )
        # Match the build/upload pipeline: only ask the LLM when the run already failed.
        # Calling AI on a clean pass invents false "failures" (e.g. LVCMOS18 on LEDs).
        ok_so_far = row["verdict"] == "pass"
        allow_ai = (not ctx.no_ai) and cfg.checks_ai and not ok_so_far
        from shepherd.llm.diagnose import ai_findings

        agent = VerifyAgent(ai_hook=ai_findings)
        verdict = agent.run(
            cfg=cfg,
            logs=logs,
            allow_ai=allow_ai,
            step="verify",
        )
        hint = display_path(run_dir.log_path("upload" if "upload" in logs else next(iter(logs))))
        _print_verdict(out, verdict.findings, hint)
        if not ctx.dry_run:
            _record_verify_run(ctx, root, cfg.board, verdict, store=store)
        return 0 if verdict.level == "pass" else 1
    finally:
        store.close()


def _record_verify_run(ctx, root, board, verdict, store: EventStore | None = None) -> None:
    """Write verify step events under ctx.run_id so the control room can light the pill."""
    from shepherd.events.db import new_run_id

    if ctx.dry_run:
        return
    own = store is None
    if store is None:
        store = EventStore.open(root)
    try:
        run = store.start_run(
            "verify",
            board=board,
            run_id=ctx.run_id or new_run_id(),
        )
        run.event("step_start", step="verify")
        payload = {
            "findings": [
                {
                    "id": f.id,
                    "level": f.level,
                    "message": f.message,
                    "cause": f.cause,
                    "fix": f.fix,
                }
                for f in verdict.findings
            ]
        }
        ok = verdict.level != "fail"
        run.event(
            "verdict",
            step="verify",
            level="error" if not ok else "info",
            message=verdict.level,
            payload=payload,
        )
        for f in verdict.findings:
            if f.cause:
                run.event("log", step="verify", level=f.level, message=f"cause: {f.cause}")
            if f.fix:
                run.event("log", step="verify", level="info", message=f"fix:   {f.fix}")
        run.event(
            "step_end",
            step="verify",
            level="error" if not ok else "info",
            payload={"ok": ok},
        )
        run.finish("fail" if not ok else "pass")
    finally:
        if own:
            store.close()


def run_check(ctx: Context, out: Output, stage: str) -> int:
    """Re-run checkpoint + VerifyAgent for one stage of the last run."""
    root, cfg = _load_cfg(ctx)
    if root is None or cfg is None:
        raise ConfigError(
            f"no {config_mod.CONFIG_NAME} found in {ctx.project} or its parents",
            hint="run `shepherd init` or pass `--project`",
        )
    store = EventStore.open(root)
    try:
        row = store.latest_run()
        if row is None:
            raise ExplainError("no runs recorded yet", hint="run `shepherd build` first")
        run_dir = RunDir(root, row["id"])
        log_name = "upload" if stage == "upload" else "build" if stage != "adapter" else "adapter"
        log_path = run_dir.log_path(log_name)
        log_text = log_path.read_text(errors="replace") if log_path.is_file() else ""
        staging_dir = root / config_mod.STATE_DIR / "build"
        checked = run_checkpoint(
            stage,
            CheckContext(
                stage=stage,
                staging_dir=staging_dir,
                cfg=cfg,
                returncode=0 if row["verdict"] == "pass" else 1,
                log_text=log_text,
            ),
        )
        agent = VerifyAgent()
        verdict = agent.run(
            cfg=cfg,
            logs={log_name: log_text},
            checkpoint_findings=list(checked.findings),
            allow_ai=False,
            step=stage,
        )
        if not checked.ok and verdict.level == "pass":
            verdict.level = "fail"
            verdict.findings = list(checked.findings) or verdict.findings
        hint = display_path(log_path) if log_path.is_file() else None
        _print_verdict(out, verdict.findings, hint)
        return 0 if verdict.level == "pass" and checked.ok else 1
    finally:
        store.close()
