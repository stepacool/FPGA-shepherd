"""Helpers for checking toolchain artifact presence and size."""

from __future__ import annotations

from pathlib import Path

# Staged toolchain cache layout (`_build/<env>/…`).
CACHE_ENV = Path("_build") / "default"

SYNTH_JSON = CACHE_ENV / "hardware.json"
PNR_JSON = CACHE_ENV / "hardware.pnr.json"
PNR_REPORT = CACHE_ENV / "hardware.pnr"
BITSTREAM = CACHE_ENV / "hardware.fs"


def exists_nonempty(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def synth_artifact(staging_dir: Path) -> Path:
    return staging_dir / SYNTH_JSON


def pnr_artifact(staging_dir: Path) -> Path | None:
    """Return the first present P&R output path, or None."""
    for rel in (PNR_JSON, PNR_REPORT):
        path = staging_dir / rel
        if path.is_file():
            return path
    return None


def bitstream_artifact(staging_dir: Path) -> Path:
    return staging_dir / BITSTREAM
