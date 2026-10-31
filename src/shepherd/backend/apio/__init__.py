"""apio build backend. Nothing outside this package knows apio exists."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from shepherd.backend.apio import parse, project, runner
from shepherd.backend.base import Staging, StepResult, StepSink
from shepherd.config import ProjectConfig


class ApioBackend:
    name = "apio"

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    def version(self) -> str | None:
        try:
            out = subprocess.run(
                [*runner.apio_argv(), "--version"], capture_output=True, text=True, timeout=30
            ).stdout
        except (OSError, subprocess.TimeoutExpired):
            return None
        match = re.search(r"version\s+(\d+\.\d+\.\d+)", out)
        return match.group(1) if match else None

    def resolve_board(self, name: str) -> str:
        return project.resolve_board(name)

    def prepare(
        self,
        cfg: ProjectConfig,
        sources: list[Path],
        constraints: Path | None,
        *,
        flash: bool = False,
    ) -> Staging:
        return project.build_staging(cfg, sources, constraints, flash=flash)

    def _run(
        self, step: str, args: list[str], staging: Staging, log_path: Path | None, sink: StepSink
    ) -> StepResult:
        argv = [*runner.apio_argv(), *args]
        sink.command(argv)
        if self.dry_run:
            return StepResult(step, True, 0, None, commands=[argv], dry_run=True)

        def on_line(line: str) -> None:
            stage = parse.detect_stage(line)
            if stage:
                sink.stage(stage)
            elif not parse.is_noise(line):
                sink.line(line)

        code = runner.run(argv, staging.dir, log_path, on_line)
        return StepResult(step, code == 0, code, log_path, commands=[argv])

    def build(
        self, staging: Staging, log_path: Path | None, sink: StepSink, *, verbose: bool = False
    ) -> StepResult:
        args = ["build", *(["--verbose-synth", "--verbose-pnr"] if verbose else [])]
        result = self._run("build", args, staging, log_path, sink)
        bitstream = project.bitstream_path(staging.dir)
        if result.ok and not result.dry_run and bitstream.is_file():
            result.artifacts["bitstream"] = bitstream
        return result

    def upload(self, staging: Staging, log_path: Path | None, sink: StepSink) -> StepResult:
        return self._run("upload", ["upload"], staging, log_path, sink)

    def passthrough(self, args: list[str], cwd: Path) -> int:
        cwd.mkdir(parents=True, exist_ok=True)
        return subprocess.call([*runner.apio_argv(), *args], cwd=cwd)
