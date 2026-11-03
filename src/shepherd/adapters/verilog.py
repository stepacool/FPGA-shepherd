"""Passthrough adapter for Verilog / SystemVerilog sources."""

from __future__ import annotations

import re
from pathlib import Path

from shepherd.config import ProjectConfig

# Constructs the open Yosys SV path does not support well enough for Shepherd v0.
_UNSUPPORTED = [
    (re.compile(r"\binterface\b"), "interface"),
    (re.compile(r"\bclass\b"), "class"),
    (re.compile(r"\bpackage\b"), "package"),
    (re.compile(r"\bunique\s+case\b"), "unique case"),
    (re.compile(r"\brandomize\b"), "randomize"),
]
_COMMENT_LINE = re.compile(r"//.*?$", re.MULTILINE)
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)


class VerilogAdapter:
    name = "verilog"

    def detect(self, cfg: ProjectConfig, sources: list[Path]) -> bool:
        """True when the project has .v/.sv sources."""
        return any(p.suffix in {".v", ".sv"} for p in sources)

    def emit(self, cfg: ProjectConfig, sources: list[Path], out_dir: Path) -> list[Path]:
        """Return Verilog/SV paths unchanged (passthrough)."""
        return [p for p in sources if p.suffix in {".v", ".sv"}]


def scan_sv_subset(sources: list[Path]) -> list[str]:
    """Return Shepherd-term error messages for unsupported SV constructs (file:line)."""
    findings: list[str] = []
    for path in sources:
        if path.suffix != ".sv" or not path.is_file():
            continue
        try:
            raw = path.read_text(errors="replace")
        except OSError:
            continue
        text = _COMMENT_BLOCK.sub("", raw)
        text = _COMMENT_LINE.sub("", text)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern, name in _UNSUPPORTED:
                if pattern.search(line):
                    findings.append(
                        f"SystemVerilog construct '{name}' at {path}:{lineno} "
                        "is not supported by the open toolchain; rewrite in "
                        "Verilog/SystemVerilog subset or split the design"
                    )
                    break
    return findings
