"""HDL adapters registry."""

from __future__ import annotations

from pathlib import Path

from shepherd.adapters.amaranth import AmaranthAdapter
from shepherd.adapters.base import Adapter
from shepherd.adapters.verilog import VerilogAdapter, scan_sv_subset
from shepherd.config import ProjectConfig

# Amaranth first so [adapters.amaranth] wins over plain Verilog sources.
_REGISTRY: list[Adapter] = [AmaranthAdapter(), VerilogAdapter()]


def register(adapter: Adapter) -> None:
    """Append an adapter to the global registry."""
    _REGISTRY.append(adapter)


def select(cfg: ProjectConfig, sources: list[Path]) -> Adapter | None:
    """Return the first registered adapter that detects this project."""
    for adapter in _REGISTRY:
        if adapter.detect(cfg, sources):
            return adapter
    return None


def all_adapters() -> list[Adapter]:
    return list(_REGISTRY)


__all__ = [
    "Adapter",
    "VerilogAdapter",
    "all_adapters",
    "register",
    "scan_sv_subset",
    "select",
]
