"""HDL adapter protocol: turn a project language into Verilog paths to stage."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from shepherd.config import ProjectConfig


class Adapter(Protocol):
    name: str

    def detect(self, cfg: ProjectConfig, sources: list[Path]) -> bool:
        """Return True if this adapter should handle the project."""
        ...

    def emit(self, cfg: ProjectConfig, sources: list[Path], out_dir: Path) -> list[Path]:
        """Return Verilog/SV paths to stage (may write generated files under out_dir)."""
        ...
