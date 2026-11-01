"""`shepherd init`: write/adopt shepherd.toml and install the toolchain."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from shepherd import adopt
from shepherd import config as config_mod
from shepherd.backend import get_backend
from shepherd.backend.base import NullSink, StepSink
from shepherd.context import Context
from shepherd.errors import EnvironmentProblem, ShepherdError
from shepherd.output import Output, display_path


@dataclass
class InitResult:
    project: str
    board: str
    top: str
    sources: list[str]
    constraints: str | None
    wrote_toml: bool
    toolchain_ok: bool
    notes: list[str]
    dry_run: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class _ToolchainSink(NullSink):
    """Forward progress lines to Output; strip backend product names from display."""

    def __init__(self, out: Output, show_commands: bool):
        self.out = out
        self.show_commands = show_commands

    def command(self, argv: list[str]) -> None:
        if self.show_commands:
            self.out.backend_command(argv, force=True)

    def line(self, text: str) -> None:
        # Keep noise down; verbose mode shows more via Output.raw elsewhere.
        lower = text.lower()
        if "error" in lower or "fail" in lower:
            self.out.detail(text, "red")
        elif "install" in lower or "download" in lower or "extract" in lower:
            self.out.detail(text, "dim")


def run_init(ctx: Context, out: Output, path: Path | None = None) -> InitResult:
    root = (path or ctx.project).resolve()
    root.mkdir(parents=True, exist_ok=True)

    proposal = adopt.propose(root)
    cfg = proposal.cfg
    wrote = False

    out.headline(f"project: {display_path(root)}")

    if proposal.created:
        if ctx.dry_run:
            out.detail(f"would write {config_mod.CONFIG_NAME}", "dim")
        else:
            text = config_mod.dump(cfg)
            (root / config_mod.CONFIG_NAME).write_text(text)
            wrote = True
            out.detail(f"wrote {config_mod.CONFIG_NAME}")
    else:
        out.detail(f"found {config_mod.CONFIG_NAME}")

    out.detail(f"board={cfg.board}  top={cfg.top}")
    out.detail(f"sources={cfg.sources}")
    if cfg.constraints:
        out.detail(f"constraints={cfg.constraints}")
    for note in proposal.notes:
        out.detail(note, "dim")

    backend = get_backend(dry_run=ctx.dry_run)
    out.headline("toolchain")
    sink: StepSink = _ToolchainSink(out, show_commands=ctx.show_backend or ctx.dry_run)
    try:
        step = backend.ensure_toolchain(sink)
    except ShepherdError:
        raise
    except OSError as e:
        raise EnvironmentProblem(
            "internet required for toolchain install",
            hint="connect to the network and re-run `shepherd init`",
        ) from e

    if not step.ok and not ctx.dry_run:
        raise EnvironmentProblem(
            "toolchain install failed",
            hint="connect to the network and re-run `shepherd init` (or `shepherd doctor --fix`)",
        )

    out.detail("packages ready" if not ctx.dry_run else "would install toolchain packages", "dim")
    out.detail("if the board is not detected later: shepherd doctor --fix", "dim")

    result = InitResult(
        project=str(root),
        board=cfg.board,
        top=cfg.top,
        sources=list(cfg.sources),
        constraints=cfg.constraints,
        wrote_toml=wrote,
        toolchain_ok=step.ok,
        notes=list(proposal.notes),
        dry_run=ctx.dry_run,
    )
    if ctx.json:
        import json

        from typer import echo

        echo(json.dumps(result.to_dict()))
    return result
