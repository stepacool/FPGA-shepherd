# Extending Shepherd

Short notes for contributors. Keep Shepherd-facing messages free of backend product names.

## Adding an HDL adapter

1. Implement `detect(cfg, sources) -> bool` and `emit(cfg, sources, out_dir) -> list[Path]` (see `src/shepherd/adapters/base.py`).
2. Register the adapter in `src/shepherd/adapters/__init__.py` (order matters: more specific first).
3. For SystemVerilog, prefer the open-toolchain subset; unsupported constructs are flagged by `scan_sv_subset`.

## Adding an error signature

Add a YAML entry under `src/shepherd/knowledge/errors/`:

```yaml
- id: tool-short-name
  tool: nextpnr
  match: "regex with (?P<name>groups)"
  cause: "Shepherd-terms cause using {name}"
  fix: "Shepherd-terms fix"
  docs: []
```

First match per tool wins (YAML order = priority). Avoid catch-alls that steal better matches.

## Agents

- **VerifyAgent** (`agents/verify.py`): checkpoints → signatures → optional AI.
- **Doctor** (`doctor.py`): environment checklist; `--fix` for non-destructive installs.
- Orchestrator stays in `pipeline.py` / `secondary.py` (deterministic).

## Backend

All toolchain calls go through `shepherd.backend.get_backend()`. Only `backend/apio/` may import or name the underlying tool. User-facing lines go through `translate_line`.

## `shepherd report --json`

Stdout is a single JSON object:

```json
{
  "command": "report",
  "verdict": "pass",
  "log": ".shepherd/runs/.../report.log",
  "fmax_mhz": 45.2,
  "raw_lines": 120
}
```

`fmax_mhz` may be `null` if the log has no parseable MHz value. Human text goes to stderr when `--json` is set.
