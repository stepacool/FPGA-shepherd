"""Load and match deterministic error signatures from knowledge/errors/*.yaml."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any

import yaml


@dataclass(frozen=True)
class Signature:
    id: str
    tool: str
    pattern: re.Pattern[str]
    cause: str
    fix: str
    docs: tuple[str, ...] = ()
    level: str = "error"

    def match(self, text: str) -> re.Match[str] | None:
        return self.pattern.search(text)


@dataclass(frozen=True)
class Match:
    signature: Signature
    groups: dict[str, str]
    cause: str
    fix: str
    level: str


def _format(template: str, groups: dict[str, str], extras: dict[str, str]) -> str:
    data = {**extras, **groups}
    try:
        return template.format_map(data)
    except (KeyError, ValueError, IndexError):
        return template


@lru_cache(maxsize=1)
def load_signatures() -> tuple[Signature, ...]:
    root = files("shepherd.knowledge").joinpath("errors")
    loaded: list[Signature] = []
    for name in ("yosys.yaml", "nextpnr.yaml", "openfpgaloader.yaml", "backend.yaml"):
        raw = yaml.safe_load(root.joinpath(name).read_text(encoding="utf-8")) or []
        for entry in raw:
            loaded.append(_from_entry(entry))
    return tuple(loaded)


def _from_entry(entry: dict[str, Any]) -> Signature:
    return Signature(
        id=entry["id"],
        tool=entry["tool"],
        pattern=re.compile(entry["match"]),
        cause=entry["cause"],
        fix=entry["fix"],
        docs=tuple(entry.get("docs") or ()),
        level=entry.get("level", "error"),
    )


_OBUF_PORT = re.compile(r"^(?P<base>[A-Za-z_][\w$]*?)_OBUF(?:_O(?:_(?P<idx>\d+))?)?$")


def normalize_io_port(port: str) -> str:
    """Map tool buffer names like `led_OBUF_O_5` back toward the design/CST net."""
    m = _OBUF_PORT.fullmatch(port)
    if not m:
        return port
    base = m.group("base")
    idx = m.group("idx")
    return f"{base}[{idx}]" if idx is not None else base


def match_log(text: str, *, constraints: str | None = None) -> list[Match]:
    """Return signature matches for `text` (first match per tool; YAML order = priority)."""
    extras = {"constraints": constraints or "the constraints file (.cst)"}
    found: list[Match] = []
    seen_ids: set[str] = set()
    seen_tools: set[str] = set()
    for sig in load_signatures():
        if sig.id in seen_ids or sig.tool in seen_tools:
            continue
        m = sig.match(text)
        if m is None:
            continue
        groups = {k: v for k, v in m.groupdict().items() if v is not None}
        if "port" in groups:
            groups["port"] = normalize_io_port(groups["port"])
        seen_ids.add(sig.id)
        seen_tools.add(sig.tool)
        found.append(
            Match(
                signature=sig,
                groups=groups,
                cause=_format(sig.cause, groups, extras),
                fix=_format(sig.fix, groups, extras),
                level=sig.level,
            )
        )
    # Drop catch-all generics when a more specific signature also matched.
    specific = [m for m in found if not m.signature.id.endswith("-generic-error")]
    return specific or found
