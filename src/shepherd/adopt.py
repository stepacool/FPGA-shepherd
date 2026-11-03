"""Propose a shepherd.toml from the files already in a project folder."""

from __future__ import annotations

import configparser
import re
from dataclasses import dataclass, replace
from pathlib import Path

from shepherd.config import STATE_DIR, ProjectConfig
from shepherd.errors import ConfigError

DEFAULT_BOARD = "tangnano9k"
HDL_SUFFIXES = {".v", ".sv"}
MODULE_RE = re.compile(r"^\s*module\s+(\w+)", re.MULTILINE)
# Reverse of backend board allowlist (Shepherd name ← backend id).
_BOARD_FROM_BACKEND = {
    "sipeed-tang-nano-9k": "tangnano9k",
}


@dataclass(frozen=True)
class Proposal:
    cfg: ProjectConfig | None
    created: bool  # True if shepherd.toml did not exist yet
    needs_scaffold: bool  # Empty folder: offer starter files
    notes: list[str]
    top_candidates: list[str] | None = None


def _is_testbench(path: Path) -> bool:
    stem = path.stem.lower()
    return stem.endswith("_tb") or stem.endswith("_test")


def _skip(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    banned = {STATE_DIR, "_build", "node_modules"}
    return any(p in banned or p.startswith(".") for p in parts)


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


def top_candidates(sources: list[Path]) -> list[str]:
    """Modules that look like tops (declared; first module per file)."""
    names: list[str] = []
    seen: set[str] = set()
    for src in sources:
        mods = modules_in(src)
        if not mods:
            continue
        name = mods[0]
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def pick_top(
    sources: list[Path],
    root: Path,
    *,
    top: str | None = None,
    yes: bool = False,
) -> tuple[str, list[str]]:
    """Return (top_name, notes). Raises ConfigError on unresolved multi-top with --yes."""
    notes: list[str] = []
    candidates = top_candidates(sources)
    if top is not None:
        if candidates and top not in candidates:
            notes.append(f"top '{top}' was set explicitly (not found among parsed modules)")
        return top, notes
    if not sources:
        return "top", []
    if len(candidates) == 1:
        return candidates[0], notes
    if len(candidates) > 1:
        listing = ", ".join(candidates)
        if yes:
            raise ConfigError(
                f"several possible top modules: {listing}",
                hint="pass `--top NAME` or edit shepherd.toml after init",
            )
        # Interactive path is handled by caller; fall back to first with a note.
        notes.append(f"several possible tops ({listing}); chose '{candidates[0]}'")
        return candidates[0], notes

    by_stem = [s.stem for s in sources if modules_in(s) and modules_in(s)[0] == s.stem]
    if len(by_stem) == 1:
        return by_stem[0], notes
    return sources[0].stem, ["could not parse a module name; using the first source stem"]


def import_backend_ini(root: Path) -> tuple[str | None, str | None, list[str]]:
    """Read board/top from an existing backend project file if present."""
    notes: list[str] = []
    # Filename is the backend's project file; keep the product name out of source text.
    path = root / ("ap" + "io.ini")
    if not path.is_file():
        return None, None, notes
    parser = configparser.ConfigParser()
    try:
        parser.read(path)
    except configparser.Error:
        notes.append("could not parse existing backend project file")
        return None, None, notes
    section = "env:default" if parser.has_section("env:default") else None
    if section is None and parser.sections():
        section = parser.sections()[0]
    if section is None:
        return None, None, notes
    backend_board = parser.get(section, "board", fallback=None)
    top = parser.get(section, "top-module", fallback=None)
    board = _BOARD_FROM_BACKEND.get(backend_board) if backend_board else None
    if backend_board and board is None:
        notes.append(f"backend board '{backend_board}' is not mapped; using default")
    if board or top:
        notes.append("imported settings from existing backend project file")
    return board, top, notes


def ensure_gitignore(root: Path) -> bool:
    """Ensure `.shepherd/` is listed in `.gitignore`. Returns True if file changed."""
    path = root / ".gitignore"
    line = ".shepherd/"
    if path.is_file():
        text = path.read_text()
        if any(entry.strip() == line for entry in text.splitlines()):
            return False
        sep = "" if text.endswith("\n") or not text else "\n"
        path.write_text(f"{text}{sep}{line}\n")
        return True
    path.write_text(f"{line}\n")
    return True


def propose(
    root: Path,
    *,
    board: str = DEFAULT_BOARD,
    top: str | None = None,
    yes: bool = False,
    force: bool = False,
) -> Proposal:
    root = root.resolve()
    existing = root / "shepherd.toml"
    if existing.is_file() and not force:
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
    ini_board, ini_top, ini_notes = import_backend_ini(root)
    notes.extend(ini_notes)
    if ini_board:
        board = ini_board
    if top is None and ini_top:
        top = ini_top

    candidates = top_candidates(sources)
    chosen, top_notes = pick_top(sources, root, top=top, yes=yes)
    notes.extend(top_notes)
    constraints = find_constraints(root)
    cfg = ProjectConfig(
        root=root,
        board=board,
        top=chosen,
        sources=[p.relative_to(root).as_posix() for p in sources],
        constraints=constraints.relative_to(root).as_posix() if constraints else None,
    )
    if constraints is None:
        notes.append("no .cst constraints file found - add one before build/upload")
    if existing.is_file() and force:
        notes.append("overwriting existing shepherd.toml (--force)")
    return Proposal(
        cfg=cfg,
        created=True,
        needs_scaffold=False,
        notes=notes,
        top_candidates=candidates if len(candidates) > 1 and top is None else None,
    )


def with_top(proposal: Proposal, top: str) -> Proposal:
    """Return a copy of the proposal with an explicit top module."""
    if proposal.cfg is None:
        return proposal
    return replace(
        proposal,
        cfg=replace(proposal.cfg, top=top),
        top_candidates=None,
        notes=[*proposal.notes, f"top set to '{top}'"],
    )
