"""`shepherd doctor`: environment checklist and optional --fix."""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from shepherd import __version__
from shepherd import config as config_mod
from shepherd.backend import Backend, get_backend
from shepherd.backend.base import NullSink
from shepherd.context import Context
from shepherd.errors import ShepherdError
from shepherd.events.db import EventStore, new_run_id
from shepherd.llm.envfile import load_dotenv
from shepherd.output import Output

FTDI_ID = "0403:6010"


@dataclass
class CheckItem:
    id: str
    status: str  # ok | warn | fail
    message: str
    fix: str | None = None
    destructive: bool = False


@dataclass
class DoctorReport:
    items: list[CheckItem]
    fixed: list[str]

    def to_dict(self) -> dict:
        return {
            "items": [asdict(i) for i in self.items],
            "fixed": list(self.fixed),
            "ok": all(i.status != "fail" for i in self.items),
        }


def _python_ok() -> CheckItem:
    major, minor = sys.version_info[:2]
    ok = (major, minor) >= (3, 11)
    return CheckItem(
        "python",
        "ok" if ok else "fail",
        f"Python {major}.{minor} (shepherd {__version__})",
        None if ok else "install Python 3.11+",
    )


def _uv_ok() -> CheckItem:
    path = shutil.which("uv")
    if path:
        return CheckItem("uv", "ok", f"uv on PATH ({path})")
    return CheckItem(
        "uv",
        "fail",
        "uv not found on PATH",
        "install uv: curl -LsSf https://astral.sh/uv/install.sh | sh",
    )


def _backend_ok(backend: Backend) -> CheckItem:
    ver = backend.version()
    if ver:
        return CheckItem("backend", "ok", f"build backend {ver}")
    return CheckItem(
        "backend",
        "fail",
        "build backend not available",
        "run `shepherd init` or `shepherd doctor --fix`",
    )


def _toolchain_ok(backend: Backend) -> CheckItem:
    # Presence of oss-cad tools is approximated by backend version succeeding
    # and a prior packages install; a dedicated check_only would be nicer.
    ver = backend.version()
    if ver:
        return CheckItem("toolchain", "ok", "toolchain packages reachable")
    return CheckItem(
        "toolchain",
        "fail",
        "toolchain packages missing",
        "run `shepherd doctor --fix` (or `shepherd init`)",
    )


def _device_ok(backend: Backend) -> CheckItem:
    found = backend.devices()
    if found:
        return CheckItem("device", "ok", f"Tang Nano programmer seen ({FTDI_ID})")
    return CheckItem(
        "device",
        "warn",
        f"no Tang Nano programmer seen (USB {FTDI_ID})",
        "plug in the board and check the cable; then `shepherd doctor --fix`",
    )


def _os_access_ok(backend: Backend) -> CheckItem:
    if sys.platform.startswith("linux"):
        groups = set()
        try:
            import getpass
            import grp

            user = getpass.getuser()
            groups = {g.gr_name for g in grp.getgrall() if user in g.gr_mem}
            groups.add(grp.getgrgid(os.getgid()).gr_name)
        except Exception:
            pass
        if "plugdev" in groups or "dialout" in groups:
            return CheckItem("udev", "ok", "user in plugdev/dialout")
        return CheckItem(
            "udev",
            "warn",
            "user may lack serial/USB permissions",
            "; ".join(backend.install_drivers("ftdi")),
            destructive=True,
        )
    if sys.platform == "darwin":
        return CheckItem(
            "ftdi",
            "ok",
            "macOS: if programming fails, unload AppleUSBFTDI (see doctor --fix)",
        )
    return CheckItem("os", "ok", f"platform {sys.platform}")


def _project_ok(root: Path) -> CheckItem:
    proj = config_mod.find_project_root(root)
    if proj is None:
        return CheckItem("project", "ok", "no shepherd.toml here (skipped)")
    try:
        cfg = config_mod.load(proj)
        sources = config_mod.resolve_sources(cfg)
        cst = config_mod.resolve_constraints(cfg)
    except ShepherdError as e:
        return CheckItem("project", "fail", e.message, e.hint)
    if not sources:
        return CheckItem("project", "fail", "no sources resolved", "fix sources in shepherd.toml")
    if cst is None:
        return CheckItem(
            "project",
            "warn",
            "shepherd.toml ok but no .cst found",
            "add a constraints file",
        )
    return CheckItem("project", "ok", f"shepherd.toml ok (top={cfg.top})")


def _ai_ok(root: Path) -> CheckItem:
    load_dotenv(root / ".env")
    load_dotenv(Path.cwd() / ".env")
    if os.environ.get("META_API_KEY", "").strip():
        return CheckItem("ai", "ok", "META_API_KEY is set")
    return CheckItem(
        "ai",
        "warn",
        "META_API_KEY not set (AI explain/ask disabled)",
        "export META_API_KEY or add it to .env",
    )


def run_checks(backend: Backend, project: Path) -> list[CheckItem]:
    """Return the full doctor checklist for this machine/project."""
    return [
        _python_ok(),
        _uv_ok(),
        _backend_ok(backend),
        _toolchain_ok(backend),
        _device_ok(backend),
        _os_access_ok(backend),
        _project_ok(project),
        _ai_ok(project),
    ]


def apply_fixes(
    items: list[CheckItem],
    backend: Backend,
    out: Output,
    *,
    yes: bool,
) -> list[str]:
    fixed: list[str] = []
    for item in items:
        if item.status == "ok" or not item.fix:
            continue
        if item.destructive:
            out.detail(f"{item.id}: run manually:", "yellow")
            out.detail(f"  {item.fix}", "dim")
            continue
        if item.id in {"backend", "toolchain"}:
            prompt = f"Install toolchain packages for '{item.id}'?"
            if not yes and not __import__("typer").confirm(prompt, default=True):
                continue
            step = backend.ensure_toolchain(NullSink())
            if step.ok:
                fixed.append(item.id)
                out.detail(f"fixed {item.id}", "green")
            else:
                out.detail(f"could not fix {item.id}", "red")
    return fixed


def run_doctor(ctx: Context, out: Output, *, fix: bool = False) -> DoctorReport:
    """Print the checklist, optionally apply non-destructive fixes, return a report."""
    backend = get_backend(dry_run=ctx.dry_run)
    root = config_mod.find_project_root(ctx.project) or ctx.project.resolve()
    items = run_checks(backend, root)
    fixed: list[str] = []

    store = None
    run = None
    try:
        if not ctx.dry_run and (root / config_mod.CONFIG_NAME).is_file():
            store = EventStore.open(root)
            run = store.start_run("doctor", board=None, run_id=ctx.run_id or new_run_id())
        for item in items:
            if run:
                run.event("step_start", step=item.id)
                run.event(
                    "step_end",
                    step=item.id,
                    level="info" if item.status == "ok" else item.status,
                    message=item.message,
                    payload={"status": item.status, "fix": item.fix},
                )
            style = {"ok": "green", "warn": "yellow", "fail": "red"}.get(item.status, "")
            out.detail(f"{item.id:<10} {item.status:<4} {item.message}", style)
            if item.fix and item.status != "ok":
                out.detail(f"           fix: {item.fix}", "dim")

        if fix:
            fixed = apply_fixes(items, backend, out, yes=ctx.yes)
            if fixed:
                items = run_checks(backend, root)

        report = DoctorReport(items=items, fixed=fixed)
        if run:
            verdict = "pass" if report.to_dict()["ok"] else "fail"
            run.event("verdict", step="doctor", message=verdict, payload=report.to_dict())
            run.finish(verdict)
        if ctx.json:
            import typer

            typer.echo(json.dumps(report.to_dict()))
        else:
            out.verdict("pass" if report.to_dict()["ok"] else "fail")
        return report
    finally:
        if store:
            store.close()
