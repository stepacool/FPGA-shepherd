"""Start / stop / restart the Next.js control room (`web/`)."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from shepherd.context import Context
from shepherd.errors import EXIT_FAIL, EXIT_USAGE, ShepherdError
from shepherd.output import Output

PID_NAME = ".shepherd-ui.json"
DEFAULT_PORT = 3010


class UiError(ShepherdError):
    exit_code = EXIT_USAGE

    def __init__(self, message: str, hint: str | None = None, *, fail: bool = False):
        super().__init__(message, hint=hint)
        if fail:
            self.exit_code = EXIT_FAIL


def find_web_dir(project: Path | None = None) -> Path | None:
    """Locate `web/package.json` in the git checkout (wheels do not ship `web/`)."""

    def _web_under(root: Path) -> Path | None:
        web = root / "web"
        if (web / "package.json").is_file():
            return web.resolve()
        if root.name == "web" and (root / "package.json").is_file():
            return root.resolve()
        return None

    env = os.environ.get("SHEPHERD_ROOT") or os.environ.get("SHEPHERD_WEB")
    if env:
        hit = _web_under(Path(env).expanduser().resolve())
        if hit:
            return hit

    starts: list[Path] = [Path.cwd()]
    if project is not None:
        starts.append(project.resolve())
    for start in starts:
        here = start.resolve()
        for _ in range(8):
            hit = _web_under(here)
            if hit:
                return hit
            if here.parent == here:
                break
            here = here.parent

    # Editable: src/shepherd/ui_cmd.py → repo root is parents[2]
    return _web_under(Path(__file__).resolve().parents[2])


def _pid_path(web: Path) -> Path:
    return web / PID_NAME


def _read_state(web: Path) -> dict | None:
    path = _pid_path(web)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _write_state(web: Path, *, pid: int, port: int) -> None:
    _pid_path(web).write_text(json.dumps({"pid": pid, "port": port}) + "\n")


def _clear_state(web: Path) -> None:
    with contextlib.suppress(OSError):
        _pid_path(web).unlink()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _port_up(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=0.4)
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _ui_healthy(port: int) -> bool:
    """True when Next is up *and* API routes work (catches a stale/corrupt `.next`)."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/defaults", timeout=1.0) as resp:
            if resp.status != 200:
                return False
            data = json.loads(resp.read().decode())
            return isinstance(data, dict) and "blinky" in data
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return False


def _build_ok(web: Path) -> bool:
    return (web / ".next" / "BUILD_ID").is_file() and (
        web / ".next" / "server" / "app" / "api" / "defaults" / "route.js"
    ).is_file()


def _pids_on_port(port: int) -> list[int]:
    """PIDs listening on TCP `port` (best-effort; empty if tools missing)."""
    pids: set[int] = set()
    try:
        out = subprocess.run(
            ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
            check=False,
            capture_output=True,
            text=True,
        )
        for line in out.stdout.split():
            with contextlib.suppress(ValueError):
                pids.add(int(line))
    except FileNotFoundError:
        pass
    if not pids:
        try:
            out = subprocess.run(
                ["fuser", f"{port}/tcp"],
                check=False,
                capture_output=True,
                text=True,
            )
            for tok in (out.stdout or "").replace("\n", " ").split():
                with contextlib.suppress(ValueError):
                    pids.add(int(tok))
        except FileNotFoundError:
            pass
    return sorted(pids)


def _kill_pid(pid: int) -> None:
    with contextlib.suppress(OSError):
        os.killpg(pid, signal.SIGTERM)
    with contextlib.suppress(OSError):
        os.kill(pid, signal.SIGTERM)
    for _ in range(20):
        if not _alive(pid):
            return
        time.sleep(0.1)
    with contextlib.suppress(OSError):
        os.killpg(pid, signal.SIGKILL)
    with contextlib.suppress(OSError):
        os.kill(pid, signal.SIGKILL)


def _free_port(port: int) -> None:
    for pid in _pids_on_port(port):
        _kill_pid(pid)
    # Orphan next-server may keep the socket briefly.
    for _ in range(30):
        if not _port_up(port) and not _pids_on_port(port):
            return
        time.sleep(0.1)


def _require_web(project: Path | None) -> Path:
    import shutil

    web = find_web_dir(project)
    if web is None:
        raise UiError(
            "could not find web/package.json — run from the FPGA-shepherd checkout "
            "(or set SHEPHERD_ROOT), e.g. `cd …/FPGA-shepherd && uv run shepherd ui`",
        )
    if shutil.which("npm") is None:
        raise UiError("`npm` not found — install Node.js ≥ 20, then re-run")
    return web


def _project_url(project: Path, port: int, web: Path) -> str:
    """Prefer a folder with shepherd.toml; else blinky example under the repo."""
    target = project.resolve()
    if not (target / "shepherd.toml").is_file():
        blinky = web.parent / "examples" / "blinky_sv"
        if (blinky / "shepherd.toml").is_file():
            target = blinky
    return f"http://127.0.0.1:{port}/?project={target}"


def _ensure_built(web: Path, out: Output, *, force: bool = False) -> None:
    need_install = not (web / "node_modules").is_dir()
    need_build = force or not _build_ok(web)
    if not need_install and not need_build:
        return
    out.headline(
        "UI setup — building the web app (about a minute on first run)…"
        if need_install or force
        else "UI first-time setup — this can take about a minute; please wait…"
    )
    if need_install:
        out.detail("running `npm install` in web/")
        install = subprocess.run(["npm", "install"], cwd=web, check=False)
        if install.returncode != 0:
            raise UiError("`npm install` failed", fail=True)
    out.detail("running `npm run build` in web/")
    built = subprocess.run(["npm", "run", "build"], cwd=web, check=False)
    if built.returncode != 0:
        raise UiError("`npm run build` failed", fail=True)
    if not _build_ok(web):
        raise UiError("`npm run build` finished but `.next` looks incomplete", fail=True)
    out.detail("web app ready")


def _wait_healthy(port: int, *, timeout_s: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _ui_healthy(port):
            return True
        time.sleep(0.25)
    return False


def start_ui(
    ctx: Context, out: Output, *, port: int = DEFAULT_PORT, open_browser: bool = True
) -> int:
    """Install/build if needed, then `npm start` in the background."""
    web = _require_web(ctx.project)
    url = _project_url(ctx.project, port, web)

    if _ui_healthy(port):
        out.headline(f"UI: {url}")
        out.detail(f"already healthy on port {port}")
        if open_browser:
            with contextlib.suppress(Exception):
                webbrowser.open(url)
        return 0

    # Port occupied by a broken/stale Next (shell loads, APIs 500) — reclaim it.
    if _port_up(port) or _pids_on_port(port):
        out.detail(f"port {port} is up but UI APIs are unhealthy — restarting")
        _free_port(port)
        _clear_state(web)
        _ensure_built(web, out, force=True)
    else:
        _ensure_built(web, out, force=False)

    out.headline(f"UI: {url}")

    log_path = web / ".shepherd-ui.log"
    log_f = log_path.open("w")
    try:
        proc = subprocess.Popen(
            ["npm", "run", "start", "--", "-p", str(port)],
            cwd=web,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_f.close()

    if proc.pid is None:
        raise UiError("failed to start UI (no pid)", fail=True)
    _write_state(web, pid=proc.pid, port=port)
    out.detail(f"started `npm start` on port {port} (pid {proc.pid})")

    if not _wait_healthy(port):
        # Capture a hint from the log for the user.
        hint = None
        with contextlib.suppress(OSError):
            tail = log_path.read_text()[-800:].strip()
            if tail:
                hint = f"see {log_path.name}: {tail.splitlines()[-1]}"
        raise UiError(
            f"UI did not become healthy on port {port} within 20s",
            hint=hint,
            fail=True,
        )

    out.detail("stop with: shepherd ui stop")
    if open_browser:
        with contextlib.suppress(Exception):
            webbrowser.open(url)
    return 0


def stop_ui(ctx: Context, out: Output, *, port: int | None = None) -> int:
    """Stop the background UI process started by `shepherd ui`."""
    web = find_web_dir(ctx.project)
    if web is None:
        raise UiError(
            "could not find web/ — run from the FPGA-shepherd checkout (or set SHEPHERD_ROOT)",
        )

    state = _read_state(web)
    pid = int(state["pid"]) if state and "pid" in state else None
    state_port = int(state["port"]) if state and "port" in state else None
    target_port = port if port is not None else (state_port or DEFAULT_PORT)

    stopped_something = False
    if pid is not None and _alive(pid):
        out.headline(f"stopping UI (pid {pid})")
        _kill_pid(pid)
        stopped_something = True
    elif pid is not None:
        out.detail(f"recorded pid {pid} is gone")

    # Reclaim orphans (next-server often outlives the npm parent).
    leftovers = _pids_on_port(target_port)
    if leftovers:
        out.detail(f"freeing port {target_port} (pids {', '.join(map(str, leftovers))})")
        _free_port(target_port)
        stopped_something = True

    _clear_state(web)
    if not stopped_something and not _port_up(target_port):
        out.detail("UI is not running (nothing to stop)")
        return 0
    if _port_up(target_port):
        out.detail(
            f"warn: port {target_port} still responds — another process may own it", "yellow"
        )
    else:
        out.detail("UI stopped")
    return 0


def restart_ui(ctx: Context, out: Output, *, port: int = DEFAULT_PORT) -> int:
    """Stop then start the UI."""
    with contextlib.suppress(UiError):
        stop_ui(ctx, out, port=port)
    return start_ui(ctx, out, port=port, open_browser=True)
