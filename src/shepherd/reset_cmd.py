"""`shepherd reset`: reset the FPGA (clear SRAM configuration)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from shepherd import config as config_mod
from shepherd.context import Context
from shepherd.errors import ConfigError, EnvironmentProblem, ShepherdError
from shepherd.events.db import EventStore, new_run_id
from shepherd.events.logs import RunDir, RunLock
from shepherd.output import Output, display_path


class ResetError(ShepherdError):
    exit_code = 2


def _loader_bin() -> str:
    """Prefer openFPGALoader on PATH (same tool the upload path uses)."""
    found = shutil.which("openFPGALoader")
    if found:
        return found
    raise EnvironmentProblem(
        "FPGA programmer tool not found",
        hint="run `shepherd doctor --fix`, then reconnect the board",
    )


def run_reset(ctx: Context, out: Output) -> int:
    """Reset the connected board so the SRAM configuration is cleared."""
    root = config_mod.find_project_root(ctx.project)
    if root is None:
        raise ConfigError(
            f"no {config_mod.CONFIG_NAME} found in {ctx.project} or its parents",
            hint="run `shepherd init` or pass `--project`",
        )
    cfg = config_mod.load(root)
    run_id = ctx.run_id or new_run_id()
    argv = [
        _loader_bin(),
        "--force-terminal-mode",
        "-b",
        cfg.board,
        "-r",
    ]

    out.headline("reset")
    out.detail(f"project: {display_path(root)}")
    out.detail(f"board:   {cfg.board}")
    out.detail("action:  reset FPGA (clear SRAM program)")
    if ctx.show_backend:
        out.detail(" ".join(argv), "dim")

    if ctx.dry_run:
        out.detail("dry run: board not touched")
        return 0

    store = EventStore.open(root)
    try:
        with RunLock(root, run_id):
            run = store.start_run("reset", board=cfg.board, run_id=run_id)
            run_dir = RunDir(root, run.id)
            run_dir.write_pid()
            log = run_dir.log_path("reset")
            run.event("step_start", step="reset")
            try:
                code = _run_loader(argv, log, run, out)
                ok = code == 0
                run.event(
                    "step_end",
                    step="reset",
                    level="info" if ok else "error",
                    message="ok" if ok else f"exit {code}",
                    payload={"ok": ok, "returncode": code, "log": str(log)},
                )
                if ok:
                    out.detail("FPGA reset — SRAM program cleared")
                    run.event("verdict", step="reset", message="pass")
                    run.finish("pass")
                    return 0
                out.detail("FPGA reset failed", "red")
                out.detail(f"log: {display_path(log)}")
                run.event(
                    "verdict",
                    step="reset",
                    level="error",
                    message="fail",
                    payload={"returncode": code},
                )
                run.finish("fail")
                return 1
            except BaseException:
                run.event("verdict", step="reset", level="error", message="error")
                run.finish("fail")
                raise
            finally:
                run_dir.remove_pid()
    finally:
        store.close()


def _run_loader(argv: list[str], log: Path, run, out: Output) -> int:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=60,
        )
    except FileNotFoundError as e:
        raise EnvironmentProblem(
            "FPGA programmer tool not found",
            hint="run `shepherd doctor --fix`, then reconnect the board",
        ) from e
    except subprocess.TimeoutExpired as e:
        raise ResetError("FPGA reset timed out", hint="unplug/replug the board and retry") from e

    text = (proc.stdout or "") + (proc.stderr or "")
    log.write_text(text)
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        run.event("log", step="reset", message=line)
        if out.ctx.verbose or out.ctx.show_backend:
            out.detail(line, "dim")
    return proc.returncode
