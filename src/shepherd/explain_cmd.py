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


def run_explain(ctx: Context, out: Output, log: Path | None) -> int:
    agent = VerifyAgent()
    if log is not None:
        path = log.expanduser().resolve()
        if not path.is_file():
            raise ExplainError(f"log file not found: {path}")
        text = path.read_text(errors="replace")
        root, cfg = _load_cfg(ctx)
        verdict = agent.explain_text(text, cfg=cfg)
        _print_verdict(out, verdict.findings, display_path(path))
        return 0 if verdict.level == "pass" else 1

    root, cfg = _load_cfg(ctx)
    if root is None:
        raise ExplainError(
            "no shepherd.toml found and no log path given",
            hint="pass a log file: `shepherd explain path/to.log`",
        )
    store = EventStore.open(root)
    try:
        row = store.latest_run()
        if row is None:
            raise ExplainError("no runs recorded yet", hint="run `shepherd build` first")
        # Prefer the latest failed run when available.
        failed = store.conn.execute(
            "SELECT * FROM runs WHERE verdict = 'fail' ORDER BY started_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
        row = failed or row
        run_dir = RunDir(root, row["id"])
        logs: dict[str, str] = {}
        for step in ("adapter", "build", "upload"):
            path = run_dir.log_path(step)
            if path.is_file():
                logs[step] = path.read_text(errors="replace")
        if not logs:
            raise ExplainError(f"no step logs for run {row['id']}")
        verdict = agent.run(cfg=cfg, logs=logs, allow_ai=False)
        hint = display_path(run_dir.log_path("build" if "build" in logs else next(iter(logs))))
        _print_verdict(out, verdict.findings, hint)
        return 0 if verdict.level == "pass" else 1
    finally:
        store.close()


def run_check(ctx: Context, out: Output, stage: str) -> int:
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
