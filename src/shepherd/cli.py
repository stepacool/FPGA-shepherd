"""`shepherd` command-line interface."""

from __future__ import annotations

import json
import signal
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from shepherd import __version__
from shepherd.context import Context
from shepherd.errors import EXIT_FAIL, EXIT_USAGE, ShepherdError
from shepherd.output import Output

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

_current: Context | None = None  # set by the root callback; read by main() for error output

app = typer.Typer(
    name="shepherd",
    help=(
        "Shepherd: set up, build, flash and diagnose FPGA projects.\n\n"
        "Typical flow: `shepherd init`, then `shepherd build` / `shepherd upload`. "
        "If the board or toolchain looks wrong: `shepherd doctor --fix`."
    ),
    context_settings=CONTEXT_SETTINGS,
    invoke_without_command=True,
    add_completion=False,
    rich_markup_mode="markdown",
)


class Stage(StrEnum):
    adapter = "adapter"
    synth = "synth"
    pnr = "pnr"
    pack = "pack"
    upload = "upload"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"shepherd {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    ctx: typer.Context,
    no_ai: Annotated[bool, typer.Option("--no-ai", help="Skip AI explanations.")] = False,
    no_check: Annotated[
        bool, typer.Option("--no-check", help="Skip checkpoint checks and verification.")
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Non-interactive: never prompt.")
    ] = False,
    json_out: Annotated[
        bool, typer.Option("--json", help="Print one machine-readable JSON result on stdout.")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would run; write and execute nothing.")
    ] = False,
    show_backend: Annotated[
        bool, typer.Option("--show-backend", help="Print the exact underlying tool commands.")
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Stream raw toolchain output.")
    ] = False,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-C", help="Project folder (default: current folder)."),
    ] = None,
    run_id: Annotated[str | None, typer.Option("--run-id", hidden=True)] = None,
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
        ),
    ] = False,
) -> None:
    global _current
    ctx.obj = _current = Context(
        no_ai=no_ai,
        no_check=no_check,
        yes=yes,
        json=json_out,
        dry_run=dry_run,
        show_backend=show_backend,
        verbose=verbose,
        project=(project or Path.cwd()).resolve(),
        run_id=run_id,
    )
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help(), nl=False)
        raise typer.Exit()


def _not_implemented(name: str) -> None:
    Console(stderr=True).print(f"shepherd {name}: not implemented yet")
    raise typer.Exit(EXIT_USAGE)


def _apply_command_flags(
    ctx: typer.Context,
    *,
    no_ai: bool = False,
    no_check: bool = False,
    yes: bool = False,
    json_out: bool = False,
    dry_run: bool = False,
    show_backend: bool = False,
    verbose: bool = False,
    project: Path | None = None,
) -> Context:
    """Merge flags passed after the subcommand into the shared Context (OR with root flags)."""
    global _current
    sctx: Context = ctx.obj
    if no_ai:
        sctx.no_ai = True
    if no_check:
        sctx.no_check = True
    if yes:
        sctx.yes = True
    if json_out:
        sctx.json = True
    if dry_run:
        sctx.dry_run = True
    if show_backend:
        sctx.show_backend = True
    if verbose:
        sctx.verbose = True
    if project is not None:
        sctx.project = project.resolve()
    _current = sctx
    return sctx


# Re-declared on implemented commands so `shepherd build --dry-run` works (not only
# `shepherd --dry-run build`). Root callback still owns the primary help listing.
_NoAi = Annotated[bool, typer.Option("--no-ai", help="Skip AI explanations.")]
_NoCheck = Annotated[
    bool, typer.Option("--no-check", help="Skip checkpoint checks and verification.")
]
_Yes = Annotated[bool, typer.Option("--yes", "-y", help="Non-interactive: never prompt.")]
_Json = Annotated[
    bool, typer.Option("--json", help="Print one machine-readable JSON result on stdout.")
]
_DryRun = Annotated[
    bool, typer.Option("--dry-run", help="Show what would run; write and execute nothing.")
]
_ShowBackend = Annotated[
    bool, typer.Option("--show-backend", help="Print the exact underlying tool commands.")
]
_Verbose = Annotated[bool, typer.Option("--verbose", "-v", help="Stream raw toolchain output.")]
_Project = Annotated[
    Path | None,
    typer.Option("--project", "-C", help="Project folder (default: current folder)."),
]


def _run_pipeline(ctx: typer.Context, command: str, flash: bool = False) -> None:
    from shepherd.pipeline import Pipeline

    sctx: Context = ctx.obj
    out = Output(sctx)
    result = Pipeline(sctx, out).run(command, flash=flash)
    if sctx.json:
        typer.echo(result.to_json())
    if result.verdict == "fail":
        raise typer.Exit(EXIT_FAIL)


@app.command()
def doctor(
    fix: Annotated[bool, typer.Option("--fix", help="Propose and apply fixes.")] = False,
) -> None:
    """Check the environment: toolchain, drivers, connected board, project."""
    _not_implemented("doctor")


@app.command()
def init(
    ctx: typer.Context,
    path: Annotated[Path | None, typer.Argument(help="Project folder (default: current).")] = None,
    no_ai: _NoAi = False,
    no_check: _NoCheck = False,
    yes: _Yes = False,
    json_out: _Json = False,
    dry_run: _DryRun = False,
    show_backend: _ShowBackend = False,
    verbose: _Verbose = False,
    project: _Project = None,
) -> None:
    """Set up a project: write or adopt shepherd.toml and install the toolchain."""
    from shepherd.init_cmd import run_init

    sctx = _apply_command_flags(
        ctx,
        no_ai=no_ai,
        no_check=no_check,
        yes=yes,
        json_out=json_out,
        dry_run=dry_run,
        show_backend=show_backend,
        verbose=verbose,
        project=project,
    )
    if path is not None:
        sctx.project = path.resolve()
    try:
        run_init(sctx, Output(sctx), path)
    except ShepherdError as e:
        _print_error(e)
        raise typer.Exit(e.exit_code) from e


@app.command()
def build(
    ctx: typer.Context,
    no_ai: _NoAi = False,
    no_check: _NoCheck = False,
    yes: _Yes = False,
    json_out: _Json = False,
    dry_run: _DryRun = False,
    show_backend: _ShowBackend = False,
    verbose: _Verbose = False,
    project: _Project = None,
) -> None:
    """Build the bitstream: HDL adapter, synth, place and route, pack, verify."""
    _apply_command_flags(
        ctx,
        no_ai=no_ai,
        no_check=no_check,
        yes=yes,
        json_out=json_out,
        dry_run=dry_run,
        show_backend=show_backend,
        verbose=verbose,
        project=project,
    )
    _run_pipeline(ctx, "build")


@app.command()
def upload(
    ctx: typer.Context,
    flash: Annotated[
        bool, typer.Option("--flash", help="Write to flash (persists). Default: SRAM.")
    ] = False,
    no_ai: _NoAi = False,
    no_check: _NoCheck = False,
    yes: _Yes = False,
    json_out: _Json = False,
    dry_run: _DryRun = False,
    show_backend: _ShowBackend = False,
    verbose: _Verbose = False,
    project: _Project = None,
) -> None:
    """Build and program the board (SRAM by default)."""
    _apply_command_flags(
        ctx,
        no_ai=no_ai,
        no_check=no_check,
        yes=yes,
        json_out=json_out,
        dry_run=dry_run,
        show_backend=show_backend,
        verbose=verbose,
        project=project,
    )
    _run_pipeline(ctx, "upload", flash=flash)


@app.command()
def lint() -> None:
    """Lint the HDL sources."""
    _not_implemented("lint")


@app.command()
def sim(
    testbench: Annotated[str | None, typer.Argument(help="Testbench to simulate.")] = None,
) -> None:
    """Simulate a testbench and save the waveform."""
    _not_implemented("sim")


@app.command()
def test(
    testbench: Annotated[str | None, typer.Argument(help="Run only this testbench.")] = None,
) -> None:
    """Run testbenches (files named *_tb.v / *_tb.sv)."""
    _not_implemented("test")


@app.command()
def report() -> None:
    """Report utilization and timing (fmax)."""
    _not_implemented("report")


@app.command()
def check(
    ctx: typer.Context,
    stage: Annotated[Stage, typer.Option("--stage", help="Stage to re-check.")],
    no_ai: _NoAi = False,
    no_check: _NoCheck = False,
    yes: _Yes = False,
    json_out: _Json = False,
    dry_run: _DryRun = False,
    show_backend: _ShowBackend = False,
    verbose: _Verbose = False,
    project: _Project = None,
) -> None:
    """Re-run the checkpoint and verification for a stage of the last run."""
    from shepherd.explain_cmd import run_check

    sctx = _apply_command_flags(
        ctx,
        no_ai=no_ai,
        no_check=no_check,
        yes=yes,
        json_out=json_out,
        dry_run=dry_run,
        show_backend=show_backend,
        verbose=verbose,
        project=project,
    )
    try:
        code = run_check(sctx, Output(sctx), stage.value)
    except ShepherdError as e:
        _print_error(e)
        raise typer.Exit(e.exit_code) from e
    raise typer.Exit(code)


@app.command()
def explain(
    ctx: typer.Context,
    log: Annotated[Path | None, typer.Argument(help="Log file (default: last failed run).")] = None,
    no_ai: _NoAi = False,
    no_check: _NoCheck = False,
    yes: _Yes = False,
    json_out: _Json = False,
    dry_run: _DryRun = False,
    show_backend: _ShowBackend = False,
    verbose: _Verbose = False,
    project: _Project = None,
) -> None:
    """Diagnose the last failure, or any log file."""
    from shepherd.explain_cmd import run_explain

    sctx = _apply_command_flags(
        ctx,
        no_ai=no_ai,
        no_check=no_check,
        yes=yes,
        json_out=json_out,
        dry_run=dry_run,
        show_backend=show_backend,
        verbose=verbose,
        project=project,
    )
    try:
        code = run_explain(sctx, Output(sctx), log)
    except ShepherdError as e:
        _print_error(e)
        raise typer.Exit(e.exit_code) from e
    raise typer.Exit(code)


@app.command()
def ask(
    ctx: typer.Context,
    question: Annotated[str, typer.Argument(help="Your question.")],
    no_ai: _NoAi = False,
    no_check: _NoCheck = False,
    yes: _Yes = False,
    json_out: _Json = False,
    dry_run: _DryRun = False,
    show_backend: _ShowBackend = False,
    verbose: _Verbose = False,
    project: _Project = None,
) -> None:
    """Ask a question with the project and last run as context."""
    from shepherd.ask_cmd import run_ask

    sctx = _apply_command_flags(
        ctx,
        no_ai=no_ai,
        no_check=no_check,
        yes=yes,
        json_out=json_out,
        dry_run=dry_run,
        show_backend=show_backend,
        verbose=verbose,
        project=project,
    )
    try:
        code = run_ask(sctx, Output(sctx), question)
    except ShepherdError as e:
        _print_error(e)
        raise typer.Exit(e.exit_code) from e
    raise typer.Exit(code)


@app.command()
def ui() -> None:
    """Open the live web view for this project (optional)."""
    _not_implemented("ui")


@app.command("help")
def help_(
    ctx: typer.Context,
    command: Annotated[str | None, typer.Argument(help="Command to show help for.")] = None,
) -> None:
    """Show help for Shepherd or one command."""
    root_ctx = ctx.parent
    assert root_ctx is not None
    group = root_ctx.command
    if command is None:
        typer.echo(group.get_help(root_ctx), nl=False)
        return
    sub = group.get_command(root_ctx, command)
    if sub is None or sub.hidden:
        Console(stderr=True).print(f"unknown command '{command}'. See `shepherd --help`.")
        raise typer.Exit(EXIT_USAGE)
    with type(root_ctx)(sub, info_name=command, parent=root_ctx) as sub_ctx:
        typer.echo(sub.get_help(sub_ctx), nl=False)


@app.command(
    hidden=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def backend(ctx: typer.Context) -> None:
    """Advanced: run the underlying build backend directly (for debugging Shepherd)."""
    from shepherd import config as config_mod
    from shepherd.backend import get_backend, staging_dir

    sctx: Context = ctx.obj
    root = config_mod.find_project_root(sctx.project) or sctx.project
    raise typer.Exit(get_backend().passthrough(list(ctx.args), staging_dir(root)))


def _sigterm(signum, frame) -> None:
    raise KeyboardInterrupt


def _print_error(err: ShepherdError) -> None:
    ctx = _current or Context()
    if ctx.json:
        typer.echo(json.dumps({"verdict": None, "error": err.message, "hint": err.hint}))
    Output(ctx).error(err)


def main() -> None:
    signal.signal(signal.SIGTERM, _sigterm)
    try:
        app()  # standalone mode: handles --help, usage errors and exit codes
    except ShepherdError as e:
        _print_error(e)
        sys.exit(e.exit_code)
    except SystemExit:
        raise
    except BaseException as e:
        ctx = _current or Context()
        out = Output(ctx)
        out.detail(f"error: unexpected failure: {e}", "red")
        out.detail("re-run with -v for details", "dim")
        if ctx.verbose:
            Console(stderr=True).print_exception()
        sys.exit(EXIT_FAIL)
