"""Build capped, path-rewritten, translated prompts for diagnosis / ask."""

from __future__ import annotations

from pathlib import Path

from shepherd.backend import translate_line
from shepherd.checks.paths import PathRewriter
from shepherd.config import ProjectConfig

MAX_LOG_CHARS = 8000


def _clean_lines(text: str, rewrite: PathRewriter | None) -> str:
    out: list[str] = []
    for line in text.splitlines():
        if rewrite is not None:
            line = rewrite(line)
        translated = translate_line(line)
        if translated is None:
            continue
        out.append(translated)
    return "\n".join(out)


def trim_around_error(text: str, limit: int = MAX_LOG_CHARS) -> str:
    if len(text) <= limit:
        return text
    lower = text.lower()
    idx = lower.find("error")
    if idx < 0:
        return text[-limit:]
    start = max(0, idx - limit // 3)
    end = min(len(text), start + limit)
    return text[start:end]


def load_board_knowledge() -> str:
    from importlib.resources import files

    root = files("shepherd.knowledge")
    parts: list[str] = []
    for name in ("tangnano9k.md", "tangnano9k.pins.md", "tangnano9k.datasheets.yaml"):
        try:
            parts.append(root.joinpath(name).read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError):
            continue
    return "\n\n".join(parts)


def build_diagnosis_messages(
    *,
    cfg: ProjectConfig | None,
    logs: dict[str, str],
    step: str | None,
    rewrite: PathRewriter | None = None,
    question: str | None = None,
) -> list[dict[str, str]]:
    chunks: list[str] = []
    if step:
        chunks.append(f"Failed step: {step}")
    if cfg is not None:
        chunks.append(
            f"shepherd.toml: board={cfg.board} top={cfg.top} sources={cfg.sources} "
            f"constraints={cfg.constraints}"
        )
        if cfg.constraints:
            cst = cfg.root / cfg.constraints
            if cst.is_file():
                chunks.append(f"constraints file `{cfg.constraints}`:\n{cst.read_text()[:2000]}")
        # Sources named in errors
        named: set[str] = set()
        combined_raw = "\n".join(logs.values())
        for src in cfg.sources:
            if Path(src).name in combined_raw or src in combined_raw:
                named.add(src)
        for src in list(named)[:4]:
            path = cfg.root / src
            if path.is_file():
                chunks.append(f"source `{src}`:\n{path.read_text()[:2000]}")

    board = load_board_knowledge()
    if board:
        chunks.append(f"Board knowledge:\n{board[:3000]}")

    log_body = trim_around_error(_clean_lines("\n".join(logs.values()), rewrite))
    chunks.append(f"Log tail:\n{log_body}")

    system = (
        "You are Shepherd, helping diagnose FPGA build/program failures. "
        'Reply with JSON only: {"cause": "...", "fix": "...", "confidence": 0.0-1.0}. '
        "Use Shepherd terms only (never mention the underlying build backend by name). "
        "Prefer concrete fixes to .cst / shepherd.toml / HDL."
    )
    if question:
        user = "Context:\n" + "\n\n".join(chunks) + f"\n\nQuestion: {question}"
        system = (
            "You are Shepherd, answering questions about an FPGA project and its last run. "
            "Be concise. Use Shepherd terms only (never name the underlying build backend)."
        )
    else:
        user = "Diagnose this failure.\n\n" + "\n\n".join(chunks)

    banned = "ap" + "io"  # backend product name must never appear in prompts
    if banned in system.lower() or banned in user.lower():
        raise RuntimeError("prompt leaked a backend product name")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
