"""VerifyAgent: deterministic facts + error signatures (+ optional AI later)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from shepherd.checks.checkpoints import Finding
from shepherd.config import ProjectConfig
from shepherd.knowledge.signatures import Match, match_log

AiHook = Callable[..., list[Finding]]


@dataclass
class Verdict:
    level: str  # pass | warn | fail
    findings: list[Finding] = field(default_factory=list)
    matched: list[Match] = field(default_factory=list)

    def to_payload(self) -> list[dict[str, Any]]:
        rows = []
        for f in self.findings:
            rows.append(
                {
                    "id": f.id,
                    "level": f.level,
                    "message": f.message,
                    "cause": f.cause,
                    "fix": f.fix,
                }
            )
        return rows


class VerifyAgent:
    def __init__(self, ai_hook: AiHook | None = None):
        self.ai_hook = ai_hook

    def run(
        self,
        *,
        cfg: ProjectConfig | None,
        logs: dict[str, str],
        checkpoint_findings: list[Finding] | None = None,
        allow_ai: bool = False,
        step: str | None = None,
    ) -> Verdict:
        """Produce a verdict from checkpoint findings, signatures, and optional AI."""
        findings = list(checkpoint_findings or [])
        combined = "\n".join(logs.values())
        constraints = cfg.constraints if cfg else None
        matches = match_log(combined, constraints=constraints)
        for m in matches:
            findings.append(
                Finding(
                    message=m.cause,
                    level=m.level,
                    id=m.signature.id,
                    cause=m.cause,
                    fix=m.fix,
                )
            )

        thin = not findings or all(f.cause is None and f.fix is None for f in findings)
        if allow_ai and thin and self.ai_hook is not None:
            findings.extend(self.ai_hook(cfg=cfg, logs=logs, step=step, existing=findings))

        if any(f.level == "error" for f in findings):
            level = "fail"
        elif any(f.level == "warn" for f in findings):
            level = "warn"
        elif not combined.strip() and not findings:
            level = "pass"
        else:
            # Logs present but no signatures: still pass if caller already marked ok.
            level = "pass" if not findings else "fail"
        return Verdict(level=level, findings=findings, matched=matches)

    def explain_text(self, text: str, *, cfg: ProjectConfig | None = None) -> Verdict:
        return self.run(cfg=cfg, logs={"log": text}, allow_ai=False)
