"""Terminal output in Shepherd terms. With --json, human output goes to stderr."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from rich.console import Console
from rich.markup import escape

from shepherd.context import Context
from shepherd.errors import ShepherdError


def display_path(path: Path) -> str:
    """Path relative to the current directory when possible."""
    try:
        rel = os.path.relpath(path)
    except ValueError:
        return str(path)
    return str(path) if rel.startswith("../..") else rel


class Output:
    def __init__(self, ctx: Context, console: Console | None = None):
        self.ctx = ctx
        self.console = console or Console(stderr=ctx.json, highlight=False, soft_wrap=True)

    def headline(self, text: str) -> None:
        self.console.print(f"[bold]→[/] {escape(text)}")

    def detail(self, text: str, style: str = "") -> None:
        body = escape(text)
        self.console.print(f"   [{style}]{body}[/]" if style else f"   {body}")

    def step(self, name: str, ok: bool, note: str = "") -> None:
        status = "[green]ok[/]" if ok else "[bold red]FAIL[/]"
        suffix = f" [dim]{escape(note)}[/]" if note else ""
        self.console.print(f"[bold]→[/] {name:<7} {status}{suffix}")

    def verdict(self, verdict: str) -> None:
        style = {"pass": "bold green", "warn": "bold yellow", "fail": "bold red"}[verdict]
        self.console.print(f"[bold]→[/] verdict: [{style}]{verdict.upper()}[/]")

    def raw(self, line: str, level: str = "info") -> None:
        if self.ctx.verbose:
            style = {"error": "red", "warn": "yellow"}.get(level, "dim")
            self.console.print(f"  [{style}]{escape(line)}[/]")

    def backend_command(self, argv: list[str], force: bool = False) -> None:
        if self.ctx.show_backend or force:
            self.console.print(f"   [dim]backend: {escape(shlex.join(argv))}[/]")

    def error(self, err: ShepherdError) -> None:
        self.console.print(f"[bold red]error:[/] {escape(err.message)}")
        if err.hint:
            self.console.print(f"  [dim]hint:[/] {escape(err.hint)}")
