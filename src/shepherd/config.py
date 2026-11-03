"""shepherd.toml: the only project file users write."""

from __future__ import annotations

import glob
import tomllib
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from shepherd.errors import ConfigError

CONFIG_NAME = "shepherd.toml"
STATE_DIR = ".shepherd"

KNOWN_KEYS = {"board", "top", "sources", "constraints", "adapters", "checks"}
GLOB_CHARS = set("*?[")


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    board: str
    top: str
    sources: list[str]
    constraints: str | None = None
    adapters: dict = field(default_factory=dict)
    checks_ai: bool = True

    @property
    def path(self) -> Path:
        return self.root / CONFIG_NAME


def find_project_root(start: Path) -> Path | None:
    """Walk up from `start` to the nearest directory containing shepherd.toml."""
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / CONFIG_NAME).is_file():
            return candidate
    return None


def load(root: Path) -> ProjectConfig:
    path = root / CONFIG_NAME
    if not path.is_file():
        raise ConfigError(
            f"no {CONFIG_NAME} found in {root}",
            hint="run `shepherd init` to create one",
        )
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{CONFIG_NAME}: invalid TOML: {e}") from e

    for key in sorted(set(data) - KNOWN_KEYS):
        warnings.warn(f"{CONFIG_NAME}: unknown key '{key}' (ignored)", stacklevel=2)

    def required_str(key: str) -> str:
        value = data.get(key)
        if value is None:
            raise ConfigError(f"{CONFIG_NAME}: '{key}' is required")
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"{CONFIG_NAME}: '{key}' must be a non-empty string")
        return value

    board = required_str("board")
    top = required_str("top")

    sources = data.get("sources")
    if sources is None:
        sources = []
    if isinstance(sources, str):
        sources = [sources]
    if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
        raise ConfigError(f"{CONFIG_NAME}: 'sources' must be a list of strings")

    constraints = data.get("constraints")
    if constraints is not None and not isinstance(constraints, str):
        raise ConfigError(f"{CONFIG_NAME}: 'constraints' must be a string path")

    adapters = data.get("adapters", {})
    if not isinstance(adapters, dict):
        raise ConfigError(f"{CONFIG_NAME}: '[adapters]' must be a table")
    if not sources and not adapters:
        raise ConfigError(
            f"{CONFIG_NAME}: 'sources' is empty and no [adapters] entry is set",
            hint="add HDL sources or an [adapters.amaranth] entry",
        )

    checks = data.get("checks", {})
    if not isinstance(checks, dict):
        raise ConfigError(f"{CONFIG_NAME}: '[checks]' must be a table")
    checks_ai = checks.get("ai", True)
    if not isinstance(checks_ai, bool):
        raise ConfigError(f"{CONFIG_NAME}: '[checks] ai' must be true or false")

    return ProjectConfig(
        root=root.resolve(),
        board=board,
        top=top,
        sources=list(sources),
        constraints=constraints,
        adapters=adapters,
        checks_ai=checks_ai,
    )


def _is_glob(pattern: str) -> bool:
    return any(c in pattern for c in GLOB_CHARS)


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def resolve_sources(cfg: ProjectConfig) -> list[Path]:
    """Expand `sources` into absolute paths.

    Explicit entries keep their order; each glob expands sorted by POSIX path.
    Duplicates are dropped (first occurrence wins).
    """
    result: list[Path] = []
    seen: set[Path] = set()
    for entry in cfg.sources:
        if _is_glob(entry):
            matches = glob.glob(entry, root_dir=cfg.root, recursive=True)
            matches = [m for m in matches if STATE_DIR not in Path(m).parts]
            if not matches:
                raise ConfigError(f"{CONFIG_NAME}: source pattern '{entry}' matched no files")
            paths = sorted(((cfg.root / m).resolve() for m in matches), key=lambda p: p.as_posix())
        else:
            path = (cfg.root / entry).resolve()
            if not path.is_file():
                raise ConfigError(f"{CONFIG_NAME}: source file '{entry}' does not exist")
            paths = [path]
        for path in paths:
            if path in seen:
                continue
            if not _inside(path, cfg.root):
                warnings.warn(f"source '{path}' is outside the project folder", stacklevel=2)
            seen.add(path)
            result.append(path)
    return result


def resolve_constraints(cfg: ProjectConfig) -> Path | None:
    """The explicit constraints file, or the single *.cst in the project."""
    if cfg.constraints:
        path = (cfg.root / cfg.constraints).resolve()
        if not path.is_file():
            raise ConfigError(f"{CONFIG_NAME}: constraints file '{cfg.constraints}' does not exist")
        return path
    found = sorted(
        p for p in cfg.root.rglob("*.cst") if STATE_DIR not in p.relative_to(cfg.root).parts
    )
    if not found:
        return None
    if len(found) > 1:
        names = ", ".join(str(p.relative_to(cfg.root)) for p in found)
        raise ConfigError(
            f"several constraint files found ({names})",
            hint=f'set `constraints = "..."` in {CONFIG_NAME}',
        )
    return found[0]


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_toml_value(v)}" for k, v in value.items()) + " }"
    raise TypeError(f"cannot write {type(value).__name__} to TOML")


def dump(cfg: ProjectConfig) -> str:
    lines = [
        f"board = {_toml_value(cfg.board)}",
        f"top = {_toml_value(cfg.top)}",
        f"sources = {_toml_value(cfg.sources)}",
    ]
    if cfg.constraints:
        lines.append(f"constraints = {_toml_value(cfg.constraints)}")
    if cfg.adapters:
        lines += ["", "[adapters]"]
        lines += [f"{name} = {_toml_value(spec)}" for name, spec in cfg.adapters.items()]
    lines += ["", "[checks]", f"ai = {_toml_value(cfg.checks_ai)}"]
    return "\n".join(lines) + "\n"
