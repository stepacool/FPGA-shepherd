"""Backend protocol: the only build-backend interface the rest of Shepherd sees."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from shepherd.config import ProjectConfig


class StepSink(Protocol):
    """Receives a backend step's progress while it runs."""

    def command(self, argv: list[str]) -> None: ...
    def stage(self, name: str) -> None: ...
    def line(self, text: str) -> None: ...


class NullSink:
    def command(self, argv: list[str]) -> None:
        pass

    def stage(self, name: str) -> None:
        pass

    def line(self, text: str) -> None:
        pass


@dataclass
class StepResult:
    step: str
    ok: bool
    returncode: int
    log_path: Path | None
    commands: list[list[str]] = field(default_factory=list)
    artifacts: dict[str, Path] = field(default_factory=dict)
    dry_run: bool = False


@dataclass
class Staging:
    """A generated backend project that points back at the user's files.

    `links` maps staged names (relative to `dir`) to user files; `files` holds generated
    file contents. Nothing is written until `write()` is called (dry-run writes nothing).
    """

    dir: Path
    links: dict[str, Path] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    keep: set[str] = field(default_factory=set)  # entries preserved across runs (build cache)

    @property
    def path_map(self) -> dict[Path, Path]:
        """Staged absolute path → user absolute path."""
        return {self.dir / name: target for name, target in self.links.items()}

    def write(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        for entry in self.dir.iterdir():
            if entry.name in self.keep:
                continue
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        for name, target in self.links.items():
            link = self.dir / name
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(os.path.relpath(target, link.parent))
        for name, content in self.files.items():
            path = self.dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)


class Backend(Protocol):
    name: str

    def version(self) -> str | None: ...

    def resolve_board(self, name: str) -> str:
        """Map a Shepherd board name to the backend's id; raise UnknownBoard if unsupported."""
        ...

    def prepare(
        self,
        cfg: ProjectConfig,
        sources: list[Path],
        constraints: Path | None,
        *,
        flash: bool = False,
    ) -> Staging: ...

    def build(
        self, staging: Staging, log_path: Path | None, sink: StepSink, *, verbose: bool = False
    ) -> StepResult: ...

    def upload(self, staging: Staging, log_path: Path | None, sink: StepSink) -> StepResult: ...

    def passthrough(self, args: list[str], cwd: Path) -> int: ...
