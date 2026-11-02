"""`shepherd ask`: Q&A with project + last run as context."""

from __future__ import annotations

from shepherd import config as config_mod
from shepherd.context import Context
from shepherd.errors import ConfigError, NetworkRequired, ShepherdError
from shepherd.events.db import EventStore
from shepherd.events.logs import RunDir
from shepherd.llm.client import LlmClient, load_config
from shepherd.llm.prompt import build_diagnosis_messages
from shepherd.output import Output


class AskError(ShepherdError):
    exit_code = 2


def run_ask(ctx: Context, out: Output, question: str) -> int:
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
    run_id = None
    store = EventStore.open(root)
    try:
        row = store.latest_run()
        if row is not None:
            run_id = row["id"]
            run_dir = RunDir(root, row["id"])
            for step in ("adapter", "build", "upload"):
                path = run_dir.log_path(step)
                if path.is_file():
                    logs[step] = path.read_text(errors="replace")
    finally:
        store.close()

    messages = build_diagnosis_messages(cfg=cfg, logs=logs, step=None, question=question)
    try:
        result = LlmClient(config).chat(messages)
    except NetworkRequired:
        raise

    answer = result.text.strip()
    out.headline("ask")
    out.detail(answer)

    if run_id is not None:
        store = EventStore.open(root)
        try:
            from shepherd.events.db import Run

            Run(store, run_id).event("ask", message=question, payload={"answer": answer})
        finally:
            store.close()
    return 0
