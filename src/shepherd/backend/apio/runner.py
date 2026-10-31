"""Runs the apio CLI as a subprocess, streaming output to a step log and a callback."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from shepherd.errors import EnvironmentProblem


def apio_argv() -> list[str]:
    """Prefer the apio installed alongside Shepherd (it is a pinned dependency)."""
    exe = Path(sys.executable).parent / ("apio.exe" if os.name == "nt" else "apio")
    if exe.is_file():
        return [str(exe)]
    return [sys.executable, "-m", "apio"]


def _terminate(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, AttributeError, PermissionError):
        proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, AttributeError, PermissionError):
            proc.kill()
        proc.wait()


def run(
    argv: list[str],
    cwd: Path,
    log_path: Path | None,
    on_line: Callable[[str], None],
) -> int:
    """Run `argv` in `cwd`; append combined output to `log_path`; return the exit code.

    The child gets its own process group so cancel (Ctrl-C / SIGTERM) can stop the whole
    toolchain tree, not just apio.
    """
    env = dict(os.environ, NO_COLOR="1", TERM="dumb", PYTHONUNBUFFERED="1")
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            errors="replace",
            start_new_session=True,
        )
    except FileNotFoundError as e:
        raise EnvironmentProblem(
            "the build backend is not installed",
            hint="reinstall Shepherd, then run `shepherd doctor --fix`",
        ) from e

    log = log_path.open("a") if log_path else None
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            if log:
                log.write(line + "\n")
                log.flush()
            on_line(line)
        return proc.wait()
    except BaseException:
        _terminate(proc)
        raise
    finally:
        if log:
            log.close()
