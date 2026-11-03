"""The orchestrator for `build` / `upload`: config → stage → backend steps → verdict.

Deterministic; no LLM. Writes the run to the events DB and step logs as it goes.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from shepherd import config as config_mod
from shepherd.agents.verify import VerifyAgent
from shepherd.backend import Backend, StepResult, get_backend
from shepherd.checks.checkpoints import CheckContext, CheckResult, Finding
from shepherd.checks.checkpoints import check as run_checkpoint
from shepherd.checks.paths import PathRewriter
from shepherd.config import ProjectConfig
from shepherd.context import Context
from shepherd.errors import ConfigError
from shepherd.events.db import EventStore, Run, new_run_id
from shepherd.events.logs import RunDir, RunLock
from shepherd.output import Output, display_path

BUILD_STAGES = ["synth", "pnr", "pack"]
MAX_ERRORS_SHOWN = 3


@dataclass
class StepRecord:
    name: str
    ok: bool
    log: str | None = None
    cached: bool = False


@dataclass
class PipelineResult:
    command: str
    board: str
    run_id: str | None
    verdict: str
    steps: list[StepRecord] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    findings: list[dict] = field(default_factory=list)
    dry_run: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self))


def hdl_label(sources: list[Path]) -> str:
    suffixes = {p.suffix for p in sources}
    if suffixes <= {".v"}:
        return "Verilog"
    if suffixes <= {".sv"}:
        return "SystemVerilog"
    if suffixes <= {".v", ".sv"}:
        return "Verilog/SystemVerilog"
    return "mixed"


def _level(line: str) -> str:
    if "ERROR" in line or line.lower().startswith("error"):
        return "error"
    if "Warning" in line or "WARNING" in line:
        return "warn"
    return "info"


class StepTracker:
    """A backend StepSink that turns tool output into events, sub-steps and terminal lines."""

    def __init__(
        self,
        step: str,
        out: Output,
        run: Run | None,
        rewrite: PathRewriter,
        log: Path | None,
        substeps: list[str] | None = None,
    ):
        self.step = step
        self.out = out
        self.run = run
        self.rewrite = rewrite
        self.log = log
        self.substeps = substeps or []
        self.current: str | None = None
        self.records: list[StepRecord] = []
        self.errors: list[str] = []

    def _event(self, kind: str, step: str, **kw) -> None:
        if self.run:
            self.run.event(kind, step=step, **kw)

    def _start(self, name: str) -> None:
        self.current = name
        self._event("step_start", name)

    def _end(self, name: str, ok: bool, returncode: int | None, cached: bool = False) -> None:
        log = str(self.log) if self.log else None
        payload = {"ok": ok, "returncode": returncode, "log": log}
        if cached:
            payload["cached"] = True
        self._event("step_end", name, level="info" if ok else "error", payload=payload)
        self.records.append(StepRecord(name, ok, log, cached))
        if not self.out.ctx.dry_run:
            self.out.step(name, ok, "up to date" if cached else "")
        self.current = None

    # StepSink -----------------------------------------------------------------

    def command(self, argv: list[str]) -> None:
        self.out.backend_command(argv, force=self.out.ctx.dry_run)

    def stage(self, name: str) -> None:
        if name not in self.substeps or name == self.current:
            return
        if self.current:
            self._end(self.current, True, 0)
        self._start(name)

    def line(self, text: str) -> None:
        from shepherd.backend import translate_line

        text = self.rewrite(text)
        translated = translate_line(text)
        if translated is None:
            return
        text = translated
        level = _level(text)
        if level == "error":
            self.errors.append(text)
        self._event("log", self.current or self.step, level=level, message=text)
        self.out.raw(text, level)

    # --------------------------------------------------------------------------

    def begin(self) -> None:
        if not self.substeps:
            self._start(self.step)

    def finish(self, result: StepResult) -> None:
        if not self.substeps:
            self._end(self.step, result.ok, result.returncode)
            return
        if self.current:
            self._end(self.current, result.ok, result.returncode)
        elif not result.ok:
            # Failed before any toolchain stage started (e.g. backend setup).
            self._end(self.step, False, result.returncode)
        if result.ok:
            # An incremental build skips stages that are already up to date.
            done = {r.name for r in self.records}
            for name in self.substeps:
                if name not in done:
                    self._start(name)
                    self._end(name, True, 0, cached=True)


class Pipeline:
    def __init__(self, ctx: Context, out: Output, backend: Backend | None = None):
        self.ctx = ctx
        self.out = out
        self.backend = backend or get_backend(dry_run=ctx.dry_run)

    def _load(self) -> ProjectConfig:
        root = config_mod.find_project_root(self.ctx.project)
        if root is None:
            raise ConfigError(
                f"no {config_mod.CONFIG_NAME} found in {self.ctx.project} or its parents",
                hint="run `shepherd init` to set up this project",
            )
        return config_mod.load(root)

    def run(self, command: str, *, flash: bool = False) -> PipelineResult:
        """Run build or upload end-to-end and return a PipelineResult."""
        from shepherd import adapters
        from shepherd.config import STATE_DIR

        cfg = self._load()
        self.backend.resolve_board(cfg.board)
        sources = config_mod.resolve_sources(cfg)
        constraints = config_mod.resolve_constraints(cfg)
        if constraints is None:
            raise ConfigError(
                "no pin constraints file (*.cst) found",
                hint=f'add one and set `constraints = "..."` in {config_mod.CONFIG_NAME}',
            )
        adapter = adapters.select(cfg, sources)
        if adapter is not None and not self.ctx.dry_run:
            # Outside the staged backend project so generated .v is not globbed twice.
            gen_dir = cfg.root / STATE_DIR / "gen"
            gen_dir.mkdir(parents=True, exist_ok=True)
            sources = adapter.emit(cfg, sources, gen_dir)
        elif adapter is not None:
            sources = adapter.emit(cfg, sources, cfg.root / STATE_DIR / "gen")
        staging = self.backend.prepare(cfg, sources, constraints, flash=flash)
        rewrite = PathRewriter(staging.path_map, staging.dir, cfg.root)
        result = PipelineResult(command=command, board=cfg.board, run_id=None, verdict="pass")
        label = adapter.name if adapter and adapter.name != "verilog" else hdl_label(sources)
        self.out.headline(f"project: {label}, top={cfg.top}, board={cfg.board}")

        if self.ctx.dry_run:
            return self._dry_run(staging, rewrite, command, result)

        run_id = self.ctx.run_id or new_run_id()
        with RunLock(cfg.root, run_id):
            store = EventStore.open(cfg.root)
            run = store.start_run(command, board=cfg.board, run_id=run_id)
            result.run_id = run.id
            run_dir = RunDir(cfg.root, run.id)
            run_dir.write_pid()
            try:
                staging.write()
                ok = self._adapter_step(run, run_dir, staging, cfg, result)
                if ok:
                    ok = self._backend_steps(command, staging, run, run_dir, rewrite, result, cfg)
                if not self.ctx.no_check:
                    ok = self._verify(cfg, run_dir, result, ok) and ok
                result.verdict = "pass" if ok else "fail"
                run.event(
                    "verdict",
                    step="verify",
                    level="info" if ok else "error",
                    message=result.verdict,
                    payload={"findings": result.findings},
                )
            except BaseException as e:
                result.verdict = "fail"
                reason = "cancelled" if isinstance(e, KeyboardInterrupt) else f"error: {e}"
                run.event("verdict", step="verify", level="error", message=reason)
                raise
            finally:
                run.finish(result.verdict)
                run_dir.remove_pid()
                store.close()
        if result.verdict == "pass":
            self._report_success(result, flash)
        return result

    def _dry_run(
        self, staging, rewrite: PathRewriter, command: str, result: PipelineResult
    ) -> PipelineResult:
        out = self.out
        out.headline("dry run: nothing will be written or executed")
        out.detail(f"staging: {display_path(staging.dir)}/")
        for name in staging.links:
            out.detail(f"  {name} -> {rewrite(str(staging.dir / name))}", "dim")
        for name, content in staging.files.items():
            out.detail(f"  {name} (generated):", "dim")
            for line in content.splitlines():
                out.detail(f"    {line}", "dim")
        tracker = StepTracker("build", out, None, rewrite, None, BUILD_STAGES)
        build = self.backend.build(staging, None, tracker, verbose=self.ctx.verbose)
        result.steps.append(StepRecord("build", build.ok))
        if command == "upload":
            tracker = StepTracker("upload", out, None, rewrite, None)
            self.backend.upload(staging, None, tracker)
            result.steps.append(StepRecord("upload", True))
        result.dry_run = True
        return result

    def _adapter_step(
        self, run: Run, run_dir: RunDir, staging, cfg: ProjectConfig, result: PipelineResult
    ) -> bool:
        # Verilog/SV passthrough: record what was staged. Other HDL adapters plug in here.
        log = run_dir.log_path("adapter")
        run.event("step_start", step="adapter")
        with log.open("w") as f:
            for name, target in staging.links.items():
                f.write(f"{name} -> {target}\n")
        run.event(
            "step_end", step="adapter", payload={"ok": True, "returncode": 0, "log": str(log)}
        )
        result.steps.append(StepRecord("adapter", True, str(log)))
        checked = self._checkpoint(
            "adapter",
            CheckContext(stage="adapter", staging_dir=staging.dir, cfg=cfg, staging=staging),
            run,
            result,
            log,
        )
        return checked.ok

    def _backend_steps(
        self,
        command: str,
        staging,
        run: Run,
        run_dir: RunDir,
        rewrite: PathRewriter,
        result: PipelineResult,
        cfg: ProjectConfig,
    ) -> bool:
        log = run_dir.log_path("build")
        tracker = StepTracker("build", self.out, run, rewrite, log, BUILD_STAGES)
        tracker.begin()
        build = self.backend.build(staging, log, tracker, verbose=self.ctx.verbose)
        tracker.finish(build)
        result.steps += tracker.records
        for kind, path in build.artifacts.items():
            run.event("artifact", step="pack", message=kind, payload={"path": str(path)})
            result.artifacts[kind] = str(path)

        log_text = log.read_text(errors="replace") if log.is_file() else ""
        for record in tracker.records:
            checked = self._checkpoint(
                record.name,
                CheckContext(
                    stage=record.name,
                    staging_dir=staging.dir,
                    cfg=cfg,
                    staging=staging,
                    returncode=build.returncode if record.name == tracker.records[-1].name else 0,
                    log_text=log_text,
                ),
                run,
                result,
                log,
            )
            if not checked.ok:
                self._report_failure(tracker, log, checked)
                return False

        if not build.ok:
            self._report_failure(tracker, log)
            return False

        if command == "upload":
            log = run_dir.log_path("upload")
            tracker = StepTracker("upload", self.out, run, rewrite, log)
            tracker.begin()
            upload = self.backend.upload(staging, log, tracker)
            tracker.finish(upload)
            result.steps += tracker.records
            log_text = log.read_text(errors="replace") if log.is_file() else ""
            checked = self._checkpoint(
                "upload",
                CheckContext(
                    stage="upload",
                    staging_dir=staging.dir,
                    cfg=cfg,
                    staging=staging,
                    returncode=upload.returncode,
                    log_text=log_text,
                ),
                run,
                result,
                log,
            )
            if not checked.ok or not upload.ok:
                self._report_failure(tracker, log, checked if not checked.ok else None)
                return False
        return True

    def _checkpoint(
        self,
        stage: str,
        ctx: CheckContext,
        run: Run,
        result: PipelineResult,
        log: Path,
    ) -> CheckResult:
        if self.ctx.no_check:
            return CheckResult(True, "checks skipped")
        checked = run_checkpoint(stage, ctx)
        if not checked.ok:
            for finding in checked.findings:
                result.findings.append(
                    {
                        "id": finding.id,
                        "level": finding.level,
                        "message": finding.message,
                        "cause": finding.cause,
                        "fix": finding.fix,
                        "stage": stage,
                    }
                )
            run.event(
                "verdict",
                step=stage,
                level="error",
                message=checked.message,
                payload={"findings": result.findings, "log": str(log)},
            )
            self.out.step(stage, False, "checkpoint")
        return checked

    def _verify(
        self, cfg: ProjectConfig, run_dir: RunDir, result: PipelineResult, ok_so_far: bool
    ) -> bool:
        logs: dict[str, str] = {}
        for step in ("adapter", "build", "upload"):
            path = run_dir.log_path(step)
            if path.is_file():
                logs[step] = path.read_text(errors="replace")
        checkpoint_findings = [
            Finding(
                message=f["message"],
                level=f.get("level", "error"),
                id=f.get("id"),
                cause=f.get("cause"),
                fix=f.get("fix"),
            )
            for f in result.findings
        ]
        allow_ai = (not self.ctx.no_ai) and cfg.checks_ai
        from shepherd.llm.diagnose import ai_findings

        verdict = VerifyAgent(ai_hook=ai_findings).run(
            cfg=cfg,
            logs=logs,
            checkpoint_findings=checkpoint_findings,
            allow_ai=allow_ai and not ok_so_far,
            step=result.command,
        )
        # Prefer signature-enriched findings when present.
        if verdict.findings:
            result.findings = verdict.to_payload()
        if not ok_so_far:
            self._report_findings(result, run_dir)
            return False
        if verdict.level == "fail":
            self._report_findings(result, run_dir)
            return False
        if verdict.level == "warn":
            for f in verdict.findings:
                if f.cause:
                    self.out.detail(f"cause: {f.cause}", "yellow")
                if f.fix:
                    self.out.detail(f"fix:   {f.fix}", "yellow")
        return True

    def _report_findings(self, result: PipelineResult, run_dir: RunDir) -> None:
        self.out.verdict("fail")
        for f in result.findings[:MAX_ERRORS_SHOWN]:
            if f.get("cause"):
                self.out.detail(f"cause: {f['cause']}")
            elif f.get("message"):
                self.out.detail(f"error: {str(f['message']).removeprefix('ERROR: ')}", "red")
            if f.get("fix"):
                self.out.detail(f"fix:   {f['fix']}")
        log = run_dir.log_path("build")
        if not log.is_file():
            log = run_dir.log_path("upload")
        if log.is_file():
            self.out.detail(f"log:   {display_path(log)}   (or re-run with -v)")

    def _report_failure(
        self, tracker: StepTracker, log: Path, checked: CheckResult | None = None
    ) -> None:
        # Defer human verdict to VerifyAgent when checks are enabled.
        if not self.ctx.no_check:
            return
        self.out.verdict("fail")
        if checked and checked.findings:
            for finding in checked.findings[:MAX_ERRORS_SHOWN]:
                self.out.detail(f"error: {finding.message.removeprefix('ERROR: ')}", "red")
                if finding.cause:
                    self.out.detail(f"cause: {finding.cause}")
                if finding.fix:
                    self.out.detail(f"fix:   {finding.fix}")
        else:
            for line in tracker.errors[:MAX_ERRORS_SHOWN]:
                self.out.detail(f"error: {line.removeprefix('ERROR: ')}", "red")
        self.out.detail(f"log:   {display_path(log)}   (or re-run with -v)")

    def _report_success(self, result: PipelineResult, flash: bool) -> None:
        self.out.verdict("pass")
        if "bitstream" in result.artifacts:
            self.out.detail(f"bitstream: {display_path(Path(result.artifacts['bitstream']))}")
        if result.command == "upload":
            if flash:
                self.out.detail("board programmed (flash: survives power cycles)")
            else:
                self.out.detail("board programmed (SRAM: lost on power cycle; --flash to keep it)")
