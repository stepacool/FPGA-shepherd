"""Rewrite staged paths (.shepherd/build/...) back to the user's own paths."""

from __future__ import annotations

import os
import re
from pathlib import Path


class PathRewriter:
    def __init__(self, path_map: dict[Path, Path], stage_dir: Path, display_root: Path):
        """`path_map`: staged absolute path → user absolute path.

        Tools see staged paths relative to `stage_dir` (e.g. `src/000_blinky.v`) or absolute.
        Both are rewritten to the user path relative to `display_root`.
        """
        pairs: dict[str, str] = {}
        for staged, user in path_map.items():
            shown = _display(user, display_root)
            pairs[str(staged)] = shown
            pairs[os.path.relpath(staged, stage_dir)] = shown
        # Longest first so absolute paths win over their relative tails.
        keys = sorted(pairs, key=len, reverse=True)
        self._pairs = pairs
        self._regex = (
            re.compile("|".join(r"(?<![\w/.-])" + re.escape(k) for k in keys)) if keys else None
        )

    def __call__(self, text: str) -> str:
        if self._regex is None:
            return text
        return self._regex.sub(lambda m: self._pairs[m.group(0)], text)


def _display(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
