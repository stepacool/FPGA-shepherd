"""Parse apio output: which toolchain stage is running, and which lines are backend noise."""

from __future__ import annotations

import re

# apio echoes each toolchain command before running it; that echo marks the stage.
STAGE_PREFIXES = (
    ("yosys ", "synth"),
    ("nextpnr", "pnr"),
    ("gowin_pack ", "pack"),
    ("openFPGALoader", "upload"),
)

# apio's own banners. Kept in the raw log file; hidden from users (they are backend terms).
NOISE = [
    re.compile(r"^Using env \S+"),
    re.compile(r"^Setting shell vars\.$"),
    re.compile(r"^-{20,}$"),
    re.compile(r"^=+ \[(SUCCESS|ERROR|FAILURE)\] .*=+$"),
    re.compile(r"^scons: "),
    re.compile(r"^No suitable cached remote config"),
    re.compile(r"^Fetching\s*$"),
    re.compile(r"^'https://github\.com/fpgawars/apio/"),
]


def detect_stage(line: str) -> str | None:
    for prefix, stage in STAGE_PREFIXES:
        if line.startswith(prefix):
            return stage
    return None


def is_noise(line: str) -> bool:
    return any(p.search(line) for p in NOISE)
