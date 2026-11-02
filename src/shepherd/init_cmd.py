"""`shepherd init`: write/adopt shepherd.toml and install the toolchain."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import typer

from shepherd import adopt, skeleton
from shepherd import config as config_mod
from shepherd.backend import get_backend
from shepherd.backend.base import NullSink, StepSink
from shepherd.context import Context
from shepherd.errors import ConfigError, ShepherdError
from shepherd.output import Output, display_path


@dataclass
class InitResult:
    project: str
    board: str
    top: str
    sources: list[str]
    constraints: str | None
    wrote_toml: bool
    scaffolded: bool
    toolchain_ok: bool
    notes: list[str]
    dry_run: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class _ToolchainSink(NullSink):
    """Forward progress lines to Output."""

    def __init__(self, out: Output, show_commands: bool):
        self.out = out
        self.show_commands = show_commands

    def command(self, argv: list[str]) -> None:
        if self.show_commands:
            self.out.backend_command(argv, force=True)

    def line(self, text: str) -> None:
        lower = text.lower()
        if "error" in lower or "fail" in lower:
            self.out.detail(text, "red")
        elif "install" in lower or "download" in lower or "extract" in lower:
            self.out.detail(text, "dim")


def _confirm_scaffold(out: Output, plan: skeleton.ScaffoldPlan, *, yes: bool) -> None:
    out.detail("no HDL found - proposed starter layout:")
    for item in plan.files:
        out.detail(f"  {item.relpath}")
    out.detail(f"board={plan.cfg.board}  top={plan.cfg.top}")
    if yes:
        return
    if not typer.confirm("Create these files?", default=True):
        raise ConfigError(
            "init cancelled",
            hint="add your HDL (and a .cst), then re-run `shepherd init`",
        )


def _apply_scaffold(
    ctx: Context, out: Output, root: Path, plan: skeleton.ScaffoldPlan
) -> adopt.Proposal:
    conflicts = plan.conflicts(root)
    if conflicts:
        names = ", ".join(display_path(p) for p in conflicts)
        raise ConfigError(
            f"refusing to replace existing file(s): {names}",
            hint="remove those file(s), then re-run `shepherd init`",
        )

    _confirm_scaffold(out, plan, yes=ctx.yes)

    if ctx.dry_run:
        out.detail("would create starter files", "dim")
        return adopt.Proposal(
            cfg=plan.cfg, created=True, needs_scaffold=False, notes=["dry-run scaffold"]
        )

    skeleton.write(root, plan)
    out.detail("created starter files")
    for item in plan.files:
        out.detail(f"  {item.relpath}", "dim")
    return adopt.Proposal(
        cfg=plan.cfg,
        created=True,
        needs_scaffold=False,
        notes=["created starter Tang Nano 9K project"],
    )


def _write_toml(ctx: Context, out: Output, cfg: config_mod.ProjectConfig) -> bool:
    if ctx.dry_run:
        out.detail(f"would write {config_mod.CONFIG_NAME}", "dim")
        return False
    (cfg.root / config_mod.CONFIG_NAME).write_text(config_mod.dump(cfg))
    out.detail(f"wrote {config_mod.CONFIG_NAME}")
    return True


def run_init(ctx: Context, out: Output, path: Path | None = None) -> InitResult:
    root = (path or ctx.project).resolve()
    root.mkdir(parents=True, exist_ok=True)

    out.headline(f"project: {display_path(root)}")
    proposal = adopt.propose(root)
    scaffolded = False

    if proposal.needs_scaffold:
        plan = skeleton.plan(root)
        proposal = _apply_scaffold(ctx, out, root, plan)
        scaffolded = not ctx.dry_run
        wrote = scaffolded  # toml included in scaffold
    elif proposal.created:
        assert proposal.cfg is not None
        wrote = _write_toml(ctx, out, proposal.cfg)
    else:
        out.detail(f"found {config_mod.CONFIG_NAME}")
        wrote = False

    cfg = proposal.cfg
    assert cfg is not None

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
        from shepherd.errors import NetworkRequired

        raise NetworkRequired("toolchain install", failed=str(e)) from e

    if not step.ok and not ctx.dry_run:
        from shepherd.errors import NetworkRequired

        raise NetworkRequired(
            "toolchain install",
            failed="toolchain package install exited non-zero",
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
        scaffolded=scaffolded,
        toolchain_ok=step.ok,
        notes=list(proposal.notes),
        dry_run=ctx.dry_run,
    )
    if ctx.json:
        import json

        typer.echo(json.dumps(result.to_dict()))
    return result
