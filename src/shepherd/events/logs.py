"""Per-run directories (.shepherd/runs/<run_id>/), step logs, PID file and the project run lock."""

from __future__ import annotations

import os
import warnings
from pathlib import Path

from shepherd.config import STATE_DIR
from shepherd.errors import RunLocked

LOCK_NAME = "lock"


class RunDir:
    def __init__(self, project_root: Path, run_id: str):
        self.path = project_root / STATE_DIR / "runs" / run_id
        self.path.mkdir(parents=True, exist_ok=True)

    def log_path(self, step: str) -> Path:
        return self.path / f"{step}.log"

    def write_pid(self) -> None:
        try:
            pgid = os.getpgid(0)
        except (AttributeError, OSError):
            pgid = ""
        (self.path / "pid").write_text(f"{os.getpid()} {pgid}\n")

    def remove_pid(self) -> None:
        (self.path / "pid").unlink(missing_ok=True)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # exists, owned by someone else
        return True
    return True


class RunLock:
    """One active run per project: `.shepherd/lock` holds "<pid> <run_id>"."""

    def __init__(self, project_root: Path, run_id: str):
        self.path = project_root / STATE_DIR / LOCK_NAME
        self.run_id = run_id
        self.held = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                if self._reclaim_stale():
                    continue
                raise RunLocked(
                    f"another Shepherd run is active in this project ({self._holder()})",
                    hint="wait for it to finish, or cancel it",
                ) from None
            with os.fdopen(fd, "w") as f:
                f.write(f"{os.getpid()} {self.run_id}\n")
            self.held = True
            return
        raise RunLocked("could not acquire the project run lock")

    def _holder(self) -> str:
        try:
            pid, run_id = self.path.read_text().split()
            return f"run {run_id}, pid {pid}"
        except (OSError, ValueError):
            return "unknown run"

    def _reclaim_stale(self) -> bool:
        try:
            pid = int(self.path.read_text().split()[0])
        except (OSError, ValueError, IndexError):
            pid = None
        if pid is not None and _pid_alive(pid):
            return False
        warnings.warn("removing a stale run lock left by a crashed run", stacklevel=2)
        self.path.unlink(missing_ok=True)
        return True

    def release(self) -> None:
        if self.held:
            self.path.unlink(missing_ok=True)
            self.held = False

    def __enter__(self) -> RunLock:
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()
