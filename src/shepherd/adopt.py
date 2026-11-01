"""Propose a shepherd.toml from the files already in a project folder."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from shepherd.config import STATE_DIR, ProjectConfig

DEFAULT_BOARD = "tangnano9k"
HDL_SUFFIXES = {".v", ".sv"}
MODULE_RE = re.compile(r"^\s*module\s+(\w+)", re.MULTILINE)


@dataclass(frozen=True)
class Proposal:
    cfg: ProjectConfig | None
    created: bool  # True if shepherd.toml did not exist yet
    needs_scaffold: bool  # Empty folder: offer starter files
    notes: list[str]


def _is_testbench(path: Path) -> bool:
    stem = path.stem.lower()
    return stem.endswith("_tb") or stem.endswith("_test")


def _skip(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    return STATE_DIR in parts or any(p.startswith(".") for p in parts)


def find_hdl(root: Path) -> list[Path]:
    return [
        p
        for p in sorted(root.rglob("*"), key=lambda p: p.as_posix())
        if p.is_file() and p.suffix in HDL_SUFFIXES and not _skip(p, root) and not _is_testbench(p)
    ]


def find_constraints(root: Path) -> Path | None:
    found = sorted(p for p in root.rglob("*.cst") if p.is_file() and not _skip(p, root))
    if len(found) == 1:
        return found[0]
    if not found:
        return None
    for p in found:
        if DEFAULT_BOARD in p.stem.lower() or "tang" in p.stem.lower():
            return p
    return found[0]


def modules_in(path: Path) -> list[str]:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return []
    return MODULE_RE.findall(text)


def pick_top(sources: list[Path], root: Path) -> tuple[str, list[str]]:
    """Return (top_name, notes). Prefer a module matching its file stem."""
    notes: list[str] = []
    if not sources:
        return "top", []

    by_stem: dict[str, Path] = {}
    all_modules: list[tuple[str, Path]] = []
    for src in sources:
        mods = modules_in(src)
        if not mods:
            continue
        all_modules.append((mods[0], src))
        if mods[0] == src.stem:
            by_stem[src.stem] = src

    if len(sources) == 1 and all_modules:
        return all_modules[0][0], notes
    if len(by_stem) == 1:
        return next(iter(by_stem)), notes
    if by_stem:
        name = sorted(by_stem)[0]
        notes.append(f"several possible tops; chose '{name}' - edit shepherd.toml if wrong")
        return name, notes
    if all_modules:
        name, src = all_modules[0]
        notes.append(f"chose top '{name}' from {src.relative_to(root)}")
        return name, notes
    return sources[0].stem, ["could not parse a module name; using the first source stem"]


def propose(root: Path, *, board: str = DEFAULT_BOARD) -> Proposal:
    root = root.resolve()
    existing = root / "shepherd.toml"
    if existing.is_file():
        from shepherd import config as config_mod

        return Proposal(
            cfg=config_mod.load(root),
            created=False,
            needs_scaffold=False,
            notes=["using existing shepherd.toml"],
        )

    sources = find_hdl(root)
    if not sources:
        return Proposal(cfg=None, created=True, needs_scaffold=True, notes=[])

    notes: list[str] = []
    top, top_notes = pick_top(sources, root)
    notes.extend(top_notes)
    constraints = find_constraints(root)
    cfg = ProjectConfig(
        root=root,
        board=board,
        top=top,
        sources=[p.relative_to(root).as_posix() for p in sources],
        constraints=constraints.relative_to(root).as_posix() if constraints else None,
    )
    if constraints is None:
        notes.append("no .cst constraints file found - add one before build/upload")
    return Proposal(cfg=cfg, created=True, needs_scaffold=False, notes=notes)
