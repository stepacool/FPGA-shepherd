"""Deterministic checkpoint checkers run after every pipeline stage."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from shepherd.backend.base import Staging
from shepherd.checks import artifacts
from shepherd.config import ProjectConfig

# Toolchain command echoes mark the active stage (same banners the backend parses).
_STAGE_PREFIXES = (
    ("yosys ", "synth"),
    ("nextpnr", "pnr"),
    ("gowin_pack ", "pack"),
    ("openFPGALoader", "upload"),
)

_UPLOAD_OK = re.compile(r"\b(Done|DONE|done)\b")
_UPLOAD_FTDI = re.compile(
    r"unable to open ftdi|no device found|device not found|permission denied",
    re.IGNORECASE,
)
_MODULE = re.compile(r"\bmodule\s+(\w+)\b", re.IGNORECASE)
_COMMENT_LINE = re.compile(r"//.*?$", re.MULTILINE)
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)


@dataclass(frozen=True)
class Finding:
    message: str
    level: str = "error"
    id: str | None = None
    cause: str | None = None
    fix: str | None = None


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    message: str
    findings: list[Finding] = field(default_factory=list)


@dataclass
class CheckContext:
    stage: str
    staging_dir: Path
    cfg: ProjectConfig
    staging: Staging | None = None
    returncode: int | None = None
    log_text: str = ""


def check(stage: str, ctx: CheckContext) -> CheckResult:
    handlers = {
        "adapter": _check_adapter,
        "synth": _check_synth,
        "pnr": _check_pnr,
        "pack": _check_pack,
        "upload": _check_upload,
    }
    handler = handlers.get(stage)
    if handler is None:
        return CheckResult(True, f"no checker for stage '{stage}'")
    return handler(ctx)


def _detect_stage(line: str) -> str | None:
    for prefix, stage in _STAGE_PREFIXES:
        if line.startswith(prefix):
            return stage
    return None


def phase_errors(log_text: str, stage: str) -> list[str]:
    """ERROR lines attributed to `stage` by walking tool banners in the log."""
    current: str | None = None
    errors: list[str] = []
    for raw in log_text.splitlines():
        detected = _detect_stage(raw)
        if detected:
            current = detected
            continue
        if current == stage and ("ERROR" in raw or raw.lower().startswith("error")):
            errors.append(raw)
    return errors


def _strip_comments(text: str) -> str:
    text = _COMMENT_BLOCK.sub("", text)
    return _COMMENT_LINE.sub("", text)


def _has_later_than_synth(staging_dir: Path) -> bool:
    return artifacts.pnr_artifact(staging_dir) is not None or artifacts.exists_nonempty(
        artifacts.bitstream_artifact(staging_dir)
    )


def _check_adapter(ctx: CheckContext) -> CheckResult:
    staging = ctx.staging
    if staging is None:
        return CheckResult(False, "adapter staging missing", [Finding("staging context missing")])

    findings: list[Finding] = []
    for name, target in staging.links.items():
        if not name.startswith("src/"):
            continue
        link = staging.dir / name
        if not link.exists():
            findings.append(Finding(f"staged source '{name}' does not resolve (broken symlink)"))
            continue
        if not target.is_file():
            findings.append(Finding(f"source '{target}' is missing"))

    top = ctx.cfg.top
    found_top = False
    for name, target in staging.links.items():
        if not name.startswith("src/") or not target.is_file():
            continue
        try:
            text = _strip_comments(target.read_text(errors="replace"))
        except OSError as e:
            findings.append(Finding(f"could not read '{target}': {e}"))
            continue
        if any(m.group(1) == top for m in _MODULE.finditer(text)):
            found_top = True
            break
    if not found_top:
        findings.append(
            Finding(
                f"top module '{top}' not found in sources",
                cause=f"no `module {top}` declaration in the listed sources",
                fix=f"set `top` in shepherd.toml to a module that exists, or add `module {top}`",
            )
        )

    if findings:
        return CheckResult(False, findings[0].message, findings)
    return CheckResult(True, "adapter sources and top module ok")


def _check_synth(ctx: CheckContext) -> CheckResult:
    errors = phase_errors(ctx.log_text, "synth")
    if errors:
        return CheckResult(False, "synth reported errors", [Finding(e) for e in errors])
    synth = artifacts.synth_artifact(ctx.staging_dir)
    if artifacts.exists_nonempty(synth) or _has_later_than_synth(ctx.staging_dir):
        return CheckResult(True, "synth ok")
    finding = Finding(f"synth output missing: {synth.name}")
    return CheckResult(False, finding.message, [finding])


def _check_pnr(ctx: CheckContext) -> CheckResult:
    errors = phase_errors(ctx.log_text, "pnr")
    if errors:
        return CheckResult(False, "place and route reported errors", [Finding(e) for e in errors])
    if artifacts.pnr_artifact(ctx.staging_dir) is not None:
        return CheckResult(True, "place and route ok")
    if artifacts.exists_nonempty(artifacts.bitstream_artifact(ctx.staging_dir)):
        return CheckResult(True, "place and route ok")
    finding = Finding("place and route output missing")
    return CheckResult(False, finding.message, [finding])


def _check_pack(ctx: CheckContext) -> CheckResult:
    bitstream = artifacts.bitstream_artifact(ctx.staging_dir)
    if not artifacts.exists_nonempty(bitstream):
        finding = Finding(f"bitstream missing or empty: {bitstream.name}")
        return CheckResult(False, finding.message, [finding])
    return CheckResult(True, "bitstream ok")


def _check_upload(ctx: CheckContext) -> CheckResult:
    findings: list[Finding] = []
    text = ctx.log_text
    if _UPLOAD_FTDI.search(text):
        findings.append(
            Finding(
                "board programmer could not open the device",
                cause="FTDI/USB device missing, busy, or permission denied",
                fix="run `shepherd doctor --fix` to repair drivers and udev rules",
            )
        )
    if ctx.returncode not in (None, 0) and not findings or ctx.returncode not in (None, 0):
        findings.append(Finding(f"upload exited with code {ctx.returncode}"))
    if not findings and not _UPLOAD_OK.search(text):
        findings.append(Finding("upload finished without a programmer success message"))
    if findings:
        return CheckResult(False, findings[0].message, findings)
    return CheckResult(True, "upload ok")
