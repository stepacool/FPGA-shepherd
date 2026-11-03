"""`shepherd ask`: Q&A with project + last run as context."""

from __future__ import annotations

from shepherd import config as config_mod
from shepherd.context import Context
from shepherd.errors import ConfigError, NetworkRequired, ShepherdError
from shepherd.events.db import EventStore, new_run_id
from shepherd.events.logs import RunDir
from shepherd.llm.client import LlmClient, load_config
from shepherd.llm.prompt import build_diagnosis_messages
from shepherd.output import Output


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
        # Prefer last build/upload for context (skip prior ask/doctor noise).
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
