"""AI diagnosis hook used by VerifyAgent when signatures are thin."""

from __future__ import annotations

from pathlib import Path

from shepherd.checks.checkpoints import Finding
from shepherd.checks.paths import PathRewriter
from shepherd.config import ProjectConfig
from shepherd.llm.client import LlmClient, load_config
from shepherd.llm.prompt import build_diagnosis_messages


def ai_findings(
    *,
    cfg: ProjectConfig | None,
    logs: dict[str, str],
    step: str | None = None,
    existing: list[Finding] | None = None,
    rewrite: PathRewriter | None = None,
    client: LlmClient | None = None,
) -> list[Finding]:
    root = cfg.root if cfg is not None else Path.cwd()
    config = load_config(root)
    if not config.enabled:
        return [
            Finding(
                message="no AI diagnosis (META_API_KEY not set)",
                level="info",
                fix="set META_API_KEY or re-run with a known error signature",
            )
        ]
    llm = client or LlmClient(config)
    messages = build_diagnosis_messages(
        cfg=cfg, logs=logs, step=step, rewrite=rewrite, question=None
    )
    result = llm.chat(messages)
    if result.parsed and {"cause", "fix"} <= set(result.parsed):
        return [
            Finding(
                message=str(result.parsed.get("cause")),
                level="error",
                id="ai-diagnosis",
                cause=str(result.parsed["cause"]),
                fix=str(result.parsed["fix"]),
            )
        ]
    return [
        Finding(
            message=result.text.strip() or "empty AI response",
            level="error",
            id="ai-unstructured",
            cause="AI (unstructured)",
            fix=result.text.strip() or None,
        )
    ]
