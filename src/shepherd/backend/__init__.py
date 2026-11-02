"""Build backend selection. `get_backend()` is the only import the rest of Shepherd uses."""

from __future__ import annotations

from pathlib import Path

from shepherd.backend.base import Backend, NullSink, Staging, StepResult, StepSink

__all__ = [
    "Backend",
    "NullSink",
    "Staging",
    "StepResult",
    "StepSink",
    "get_backend",
    "staging_dir",
    "translate_line",
]


def get_backend(dry_run: bool = False) -> Backend:
    from shepherd.backend.apio import ApioBackend

    return ApioBackend(dry_run=dry_run)


def staging_dir(project_root: Path) -> Path:
    """Path to the generated backend project for `project_root` (may not exist yet)."""
    from shepherd.backend.apio.project import staging_dir as _staging_dir

    return _staging_dir(project_root)


def translate_line(line: str) -> str | None:
    """Shepherd-facing rewrite of a backend/tool line; None means drop."""
    from shepherd.backend.apio.translate import translate_line as _translate

    return _translate(line)
