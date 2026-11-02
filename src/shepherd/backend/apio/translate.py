"""Rewrite backend-specific lines into Shepherd terms (or drop them).

Toolchain lines (yosys / nextpnr / gowin_pack / openFPGALoader) pass through untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# replacement is None → drop the line from user-facing / LLM-facing streams.
_DROP = None


@dataclass(frozen=True)
class Rule:
    pattern: re.Pattern[str]
    replacement: str | None  # None means drop


RULES: list[Rule] = [
    Rule(re.compile(r"\bapio\s+drivers\b", re.IGNORECASE), "shepherd doctor --fix"),
    Rule(re.compile(r"\bapio\s+devices\b", re.IGNORECASE), "shepherd doctor --fix"),
    Rule(
        re.compile(r"\bapio\s+packages\s+install\b", re.IGNORECASE),
        "shepherd init",
    ),
    Rule(re.compile(r"\bapio\.ini\b"), "shepherd.toml"),
    Rule(re.compile(r"^Using env \S+"), _DROP),
    Rule(re.compile(r"^Setting shell vars\.$"), _DROP),
    Rule(re.compile(r"^-{20,}$"), _DROP),
    Rule(re.compile(r"^=+ \[(SUCCESS|ERROR|FAILURE)\] .*=+$"), _DROP),
    Rule(re.compile(r"^scons: "), _DROP),
    Rule(re.compile(r"^No suitable cached remote config"), _DROP),
    Rule(re.compile(r"^Fetching\s*$"), _DROP),
    Rule(re.compile(r"^'https://github\.com/fpgawars/apio/"), _DROP),
    Rule(re.compile(r"\bapio\b", re.IGNORECASE), "the build backend"),
]


def translate_line(line: str) -> str | None:
    """Return the Shepherd-facing line, or None to drop it entirely."""
    text = line
    for rule in RULES:
        if rule.replacement is _DROP:
            if rule.pattern.search(text):
                return None
            continue
        text = rule.pattern.sub(rule.replacement, text)
    return text
