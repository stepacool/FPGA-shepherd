"""Global flags shared by every command. Commands read flags from here, never from sys.argv."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Context:
    no_ai: bool = False
    no_check: bool = False
    yes: bool = False
    json: bool = False
    dry_run: bool = False
    show_backend: bool = False
    verbose: bool = False
    project: Path = field(default_factory=Path.cwd)
    run_id: str | None = None
