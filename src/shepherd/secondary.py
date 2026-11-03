"""Thin orchestrator for lint / sim / test / report."""

from __future__ import annotations

import json
import re
from pathlib import Path

from shepherd import adapters
from shepherd import config as config_mod
from shepherd.agents.verify import VerifyAgent
from shepherd.backend import get_backend
from shepherd.checks.paths import PathRewriter
from shepherd.context import Context
from shepherd.errors import ConfigError
from shepherd.events.db import EventStore, new_run_id
from shepherd.events.logs import RunDir, RunLock
from shepherd.output import Output, display_path

_BOARD_CLOCK_MHZ = 27.0
_FMAX_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*MHz", re.IGNORECASE)


def run_secondary(
    ctx: Context,
    out: Output,
    command: str,
    testbench: str | None = None,
) -> int:
    """Run lint, sim, test, or report against the staged project."""
    root = config_mod.find_project_root(ctx.project)
    if root is None:
        raise ConfigError(
            f"no {config_mod.CONFIG_NAME} found in {ctx.project} or its parents",
            hint="run `shepherd init`",
        )
    cfg = config_mod.load(root)
    sources = config_mod.resolve_sources(cfg)
    constraints = config_mod.resolve_constraints(cfg)
    backend = get_backend(dry_run=ctx.dry_run)
    backend.resolve_board(cfg.board)
    adapter = adapters.select(cfg, sources)
    if adapter is not None:
        gen_dir = root / config_mod.STATE_DIR / "gen"
        gen_dir.mkdir(parents=True, exist_ok=True)
        sources = adapter.emit(cfg, sources, gen_dir)
    staging = backend.prepare(cfg, sources, constraints, flash=False)
    rewrite = PathRewriter(staging.path_map, staging.dir, cfg.root)

    if ctx.dry_run:
        out.headline(f"dry run: {command}")
        for name in staging.links:
            out.detail(f"  {name}", "dim")
        return 0

    run_id = ctx.run_id or new_run_id()
    with RunLock(root, run_id):
        store = EventStore.open(root)
        run = store.start_run(command, board=cfg.board, run_id=run_id)
        run_dir = RunDir(root, run.id)
        run_dir.write_pid()
        try:
            staging.write()
            log = run_dir.log_path(command)
            run.event("step_start", step=command)
            sink = _Sink(out, run, rewrite, command)
            method = getattr(backend, command)
            if command in {"sim", "test"}:
                result = method(
                    staging, log, sink, testbench=_staged_testbench(staging, testbench)
                )
            else:
                result = method(staging, log, sink)
            run.event(
                "step_end",
                step=command,
                level="info" if result.ok else "error",
                payload={"ok": result.ok, "returncode": result.returncode, "log": str(log)},
            )
            text = log.read_text(errors="replace") if log.is_file() else ""
            payload = {"log": str(log)}
            if command == "report":
                payload.update(_parse_report(text))
                _print_report(out, payload)
                if payload.get("fmax_mhz") is not None and payload["fmax_mhz"] < _BOARD_CLOCK_MHZ:
                    out.detail(
                        f"warn: fmax {payload['fmax_mhz']} MHz "
                        f"< board clock {_BOARD_CLOCK_MHZ} MHz",
                        "yellow",
                    )
            if command == "sim" and result.ok:
                vcd = _find_vcd(staging.dir)
                if vcd:
                    run.event("artifact", step="sim", message="vcd", payload={"path": str(vcd)})
                    out.detail(f"vcd: {display_path(vcd)}")
            verdict_level = "pass" if result.ok else "fail"
            if command == "lint" and result.ok and "warning" in text.lower():
                verdict_level = "warn"
            if not ctx.no_check and not result.ok:
                v = VerifyAgent().run(cfg=cfg, logs={command: text}, allow_ai=False)
                for f in v.findings[:3]:
                    if f.cause:
                        out.detail(f"cause: {f.cause}")
                    if f.fix:
                        out.detail(f"fix:   {f.fix}")
            run.event("verdict", step=command, message=verdict_level, payload=payload)
            run.finish("pass" if verdict_level != "fail" else "fail")
            out.verdict("pass" if verdict_level != "fail" else "fail")
            if ctx.json:
                import typer

                typer.echo(
                    json.dumps(
                        {
                            "command": command,
                            "verdict": verdict_level,
                            "log": str(log),
                            **{k: v for k, v in payload.items() if k != "log"},
                        }
                    )
                )
            return 0 if verdict_level != "fail" else 1
        finally:
            run_dir.remove_pid()
            store.close()


class _Sink:
    def __init__(self, out, run, rewrite, step):
        self.out = out
        self.run = run
        self.rewrite = rewrite
        self.step = step

    def command(self, argv):
        self.out.backend_command(argv)

    def stage(self, name):
        pass

    def line(self, text):
        from shepherd.backend import translate_line

        text = self.rewrite(text)
        text = translate_line(text)
        if text is None:
            return
        self.run.event("log", step=self.step, message=text)
        self.out.raw(text)


def _parse_report(text: str) -> dict:
    fmax = None
    for match in _FMAX_RE.finditer(text):
        fmax = float(match.group(1))
    return {"fmax_mhz": fmax, "raw_lines": len(text.splitlines())}


def _print_report(out: Output, payload: dict) -> None:
    if payload.get("fmax_mhz") is not None:
        out.detail(f"fmax: {payload['fmax_mhz']} MHz")
    else:
        out.detail("report finished (see log for utilization/timing)")


def _find_vcd(staging_dir: Path) -> Path | None:
    matches = list(staging_dir.rglob("*.vcd"))
    return matches[0] if matches else None


def _staged_testbench(staging, testbench: str | None) -> str | None:
    """Map a user path like rtl/blinky_tb.sv to the staged path the backend expects."""
    if not testbench:
        return None
    want = Path(testbench)
    for link, src in staging.links.items():
        name = Path(link).name
        if name.endswith(f"_{want.name}") or name == want.name:
            return link
        try:
            if src.resolve() == want.resolve() or src.name == want.name:
                return link
        except OSError:
            continue
    return testbench
