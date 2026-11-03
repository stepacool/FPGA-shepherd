"""Amaranth adapter: elaborate Python design to Verilog under .shepherd/gen/."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from shepherd.config import ProjectConfig
from shepherd.errors import ShepherdError

_ENTRY = re.compile(r"^(?P<path>.+):(?P<name>\w+)$")


class AdapterError(ShepherdError):
    exit_code = 1


class AmaranthAdapter:
    name = "amaranth"

    def detect(self, cfg: ProjectConfig, sources: list[Path]) -> bool:
        """True when [adapters.amaranth] entry is set."""
        entry = (cfg.adapters.get("amaranth") or {}).get("entry")
        return bool(entry)

    def emit(self, cfg: ProjectConfig, sources: list[Path], out_dir: Path) -> list[Path]:
        """Elaborate the Amaranth entrypoint to Verilog under out_dir."""
        spec = (cfg.adapters.get("amaranth") or {}).get("entry")
        if not spec:
            raise AdapterError("missing [adapters.amaranth] entry in shepherd.toml")
        match = _ENTRY.match(spec.strip())
        if not match:
            raise AdapterError(
                f"invalid amaranth entry '{spec}'",
                hint='use entry = "rtl/top.py:Top"',
            )
        rel = match.group("path")
        cls_name = match.group("name")
        src = cfg.root / rel
        if not src.is_file():
            raise AdapterError(f"amaranth entry file not found: {rel}")

        out_dir.mkdir(parents=True, exist_ok=True)
        out_v = out_dir / f"{cfg.top}.v"
        script = _emit_script(src, cls_name, cfg.top, out_v)
        # amaranth-yosys: PyPI Yosys fallback when no system Yosys is on PATH.
        argv = [
            "uv",
            "run",
            "--with",
            "amaranth",
            "--with",
            "amaranth-yosys",
            "python",
            "-c",
            script,
        ]
        try:
            proc = subprocess.run(argv, cwd=cfg.root, capture_output=True, text=True, timeout=180)
        except FileNotFoundError:
            # Fall back to the current interpreter if uv is unavailable.
            proc = subprocess.run(
                [sys.executable, "-c", script],
                cwd=cfg.root,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired as e:
            raise AdapterError("amaranth elaboration timed out") from e

        if proc.returncode != 0:
            raise AdapterError(_trim_traceback(proc.stderr or proc.stdout or "amaranth failed"))
        if not out_v.is_file():
            raise AdapterError(f"amaranth did not write {out_v.name}")

        # Keep any explicit Verilog sources alongside generated output.
        verilog = [p for p in sources if p.suffix in {".v", ".sv"}]
        return [*verilog, out_v]


def _emit_script(src: Path, cls_name: str, top: str, out_v: Path) -> str:
    return f"""
import importlib.util, sys
from pathlib import Path
path = Path({str(src)!r})
spec = importlib.util.spec_from_file_location("shepherd_amaranth_user", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
cls = getattr(mod, {cls_name!r})
obj = cls()
try:
    from amaranth.back import verilog
    from amaranth import Elaboratable
except ImportError as e:
    raise SystemExit("amaranth is not installed; try: uv run --with amaranth shepherd build") from e
ports = None
if hasattr(obj, "ports") and callable(obj.ports):
    ports = obj.ports()
elif hasattr(obj, "signature"):
    try:
        ports = obj.signature.members
    except Exception:
        ports = None
text = verilog.convert(obj, name={top!r}, ports=ports)
Path({str(out_v)!r}).write_text(text)
"""


def _trim_traceback(text: str) -> str:
    lines = text.strip().splitlines()
    keep: list[str] = []
    for line in lines:
        if 'File "' in line and ("site-packages" in line or "amaranth/" in line):
            continue
        keep.append(line)
    # Prefer last error line.
    msg = "\n".join(keep[-12:]) if keep else text.strip()
    return msg or "amaranth elaboration failed"
