# FPGA Shepherd — Multi-Agent FPGA Programming Toolkit

## Goal

Ship a **hackathon-ready, reusable tool** that helps people **build Tang Nano 9K projects quickly from natural language (NL)** — ordinary human wording, not code or CLI flags.

The user opens Shepherd, we ask something like **“How can we help you today?”**, they say e.g. *“help me read inertial measurement unit (IMU) sensor data on my Tang Nano 9K”*, and Meta Llama–powered agents **clarify → scaffold → validate → build → program**, with an **automatic AI check after each of validate / build / program** to judge whether things look good and what to fix next.

Colleagues and later users can run it, fork it, and add new agents/tools. **v0 board support: Tang Nano 9K only.**

## Product shape

A small **Python CLI package** (`fpga-shepherd` / `shepherd`) that:

- Starts an **interactive guided session** (prompt + clarifying questions), not only one-shot commands
- Talks to **Meta Llama** (`META_API_KEY` + `META_BASE_URL` + model id via env)
- Runs **independent specialist agents** with shared tool interfaces
- Executes FPGA work through **OSS CAD Suite CLI** (not the Lushay VS Code UI)
- Is easy to extend: new agent = new module + tool registrations + prompt

Lushay Code remains an optional human UX note in docs; agents do not drive the extension UI.

## Primary user journey (what we optimize for)

```mermaid
flowchart TD
  Start[shepherd_chat] --> Ask[How_can_we_help_today]
  Ask --> Goal[User_NL_goal]
  Goal --> Guide[GuideAgent_clarify_and_plan]
  Guide --> Confirm[User_confirms_plan]
  Confirm --> Env[EnvAgent]
  Confirm --> Toolchain[ToolchainAgent]
  Confirm --> Design[DesignAgent_scaffold_RTL_CST]
  Design --> Project[ProjectAgent_validate]
  Project --> Verify1[VerifyAgent_after_validate]
  Verify1 --> Build[BuildProgramAgent]
  Build --> Verify2[VerifyAgent_after_build_or_program]
  Verify2 --> Done[Report_next_steps]
```

### Auto-check policy (VerifyAgent)

After **every** `validate`, `build`, and `program` step (chat pipeline *and* direct CLI commands), Shepherd **always** runs **VerifyAgent**. It does not replace exit codes; it interprets them plus logs/artifacts and returns a structured verdict:

| After | What VerifyAgent checks | Verdict shape |
| --- | --- | --- |
| **validate** | Required files present, top module, `.cst` vs ports, obvious pin mistakes | `pass` / `fail` + fix list; block build on `fail` unless user overrides |
| **build** | Tool exit codes, yosys/nextpnr/gowin_pack stderr, bitstream `.fs` exists & non-empty, timing/resource warnings worth mentioning | `pass` / `warn` / `fail` + whether to retry or edit register-transfer level (RTL) code |
| **program** | openFPGALoader output, USB/device detect clues, success phrases vs cable errors | `pass` / `fail` + next human checks (LEDs, universal asynchronous receiver-transmitter (UART)) when hardware can’t be sensed |

Rules:

- Deterministic facts first (exit code, file exists); Meta Llama explains and prioritizes fixes
- On `fail`, Shepherd stops the happy-path pipeline, shows the verdict, and may loop back to Design/Project/Build with the user’s OK
- On `warn`, continue but surface warnings clearly
- VerifyAgent is independently runnable: `shepherd check --stage validate|build|program --project …`

Example:

1. Shepherd: *How can we help you today?*
2. User: *Help me read IMU sensor data on my Tang Nano 9K.*
3. GuideAgent asks only what’s needed, e.g.:
   - Which IMU / interface (Inter-Integrated Circuit (I2C)? Serial Peripheral Interface (SPI)? module name if known)?
   - Which pins / PMOD / header?
   - Output preference (LEDs, UART serial, both)?
   - New project path or existing folder?
4. Shepherd proposes a short plan (files to create, pins, build/program).
5. After user OK: scaffold Verilog + `.cst` → validate → **auto-check** → build → **auto-check** → program → **auto-check**.
6. Report success / errors and what to try next (e.g. open serial monitor), using VerifyAgent’s last verdict.

Direct commands (`doctor`, `validate`, `build`, `program`) remain available for power users; validate/build/program still trigger auto-check unless `--no-check` is passed.

## Agent map (independent, step-aligned)

```mermaid
flowchart LR
  User[User_or_CLI] --> Shepherd[Shepherd_orchestrator]
  Shepherd --> Guide[GuideAgent]
  Shepherd --> Design[DesignAgent]
  Shepherd --> Env[EnvAgent]
  Shepherd --> Toolchain[ToolchainAgent]
  Shepherd --> Project[ProjectAgent]
  Shepherd --> Build[BuildProgramAgent]
  Shepherd --> Verify[VerifyAgent]
  Guide --> Chat[clarify_questions]
  Design --> Files[write_verilog_cst]
  Env --> ShellTools[shell_fs_checks]
  Toolchain --> OssCad[oss_cad_suite_install_verify]
  Project --> VerilogCst[verilog_cst_validate]
  Build --> YosysNextpnr[yosys_nextpnr_gowin_pack]
  Build --> Loader[openFPGALoader]
  Verify --> Logs[logs_artifacts_usb]
```

| Agent | Role | Responsibility | Acts via |
| --- | --- | --- | --- |
| **Shepherd** | Orchestrator + session host | Ask how we can help; route to specialists; **always invoke VerifyAgent after validate/build/program**; keep structured session context; final report | Agent dispatch + interactive prompts |
| **GuideAgent** | Intent → plan | Parse NL goal; ask clarifying questions; produce a confirmed build plan (interfaces, pins, artifacts, success criteria). **Tang Nano 9K only** — refuse/redirect other boards | Chat + structured plan object |
| **DesignAgent** | Scaffold project | From confirmed plan, create/update project dir: `top.v` (+ modules), constraints (`.cst`), README snippet for the design | File write tools; board pin knowledge for Tang Nano 9K |
| **EnvAgent** | Step 1 (adapted) | Check Cursor/VS Code + optional Lushay Code; report readiness. Does not block CLI flow if extension missing | `cursor`/`code` extension list/install when available |
| **ToolchainAgent** | Step 2 | Detect/install/verify OSS CAD Suite; ensure `yosys`, `nextpnr-*`, `gowin_pack`, `openFPGALoader` | Download/extract, config path, smoke-test binaries |
| **ProjectAgent** | Step 3 | Validate project: ≥1 `.v`, ≥1 `.cst`, top module (`top` default), pin sanity | Filesystem + heuristics + fix suggestions |
| **BuildProgramAgent** | Step 4 | Synthesize → P&R → pack → program; capture full logs for VerifyAgent | `yosys`, nextpnr, `gowin_pack`, `openFPGALoader -b tangnano9k` |
| **VerifyAgent** | Auto-check | After validate/build/program: read exit codes, logs, artifacts (and optional USB detect); emit `pass`/`warn`/`fail` + plain-language fixes | Log/artifact tools + Meta Llama judgment |

Each specialist is **independently invokable** (`shepherd run guide`, `shepherd run design`, …) and also used inside `shepherd chat` / `shepherd run`.

## Board constraint (v0)

- **Supported boards are declared in one registry file** (see below). v0 lists **Tang Nano 9K only**.
- GuideAgent / Shepherd load that file as the allowlist — do not hardcode board names in agent prompts alone
- If the user names another board, GuideAgent explains it is unsupported and continues only if they agree to target a listed board
- Per-board pin helpers and `knowledge/*.md` stay optional extras; the registry is the source of truth for “do we support this?”

### Boards registry format

Prefer **YAML** (`boards.yaml`): easy for teammates to read/edit, comments allowed, maps cleanly to structured Python.

Canonical path: [`boards.yaml`](boards.yaml) at the **repo root** (also importable from package data if we package later).

```yaml
# boards.yaml — supported FPGA boards (source of truth for allowlist)
version: 1
default_board: tangnano9k
boards:
  tangnano9k:
    name: Tang Nano 9K
    aliases:
      - tang nano 9k
      - tangnano 9k
      - sipeed tang nano 9k
    supported: true
    vendor: Sipeed
    fpga:
      family: GW1N-9C
      device: GW1NR-LV9QN88PC6/I5
    openfpgaloader:
      board: tangnano9k
    constraints:
      extension: .cst
    notes: v0 only supported board
```

Rules:

- `boards.<id>.supported: true` is required for Shepherd to accept that board
- `default_board` must reference an existing supported id
- Adding a board later = new YAML entry + optional `knowledge/<id>.md` + tools — GuideAgent picks it up from the registry

## Default technical decisions

- **Language**: Python 3.11+
- **LLM**: Meta Llama via OpenAI-compatible HTTP client. Abstract behind `llm/client.py`
- **Agent loop**: Lightweight ReAct-style loop (model ↔ tools ↔ observation), one loop per agent — no heavy framework lock-in
- **Interaction**: `shepherd chat` is the default happy path (readline / prompt_toolkit style Q&A)
- **Boards**: YAML registry at repo root (`boards.yaml`); Tang Nano 9K only in v0
- **OS**: macOS + Linux for v0; Windows later
- **Secrets**: `.env.example` only; never commit keys

## Session context (handoff object)

Shared across agents:

```text
{
  goal,                 # original user prompt
  answers,              # Q&A from GuideAgent
  plan,                 # confirmed steps + interfaces + pins
  project_path,
  board: "tangnano9k",
  oss_cad_path,
  artifacts,            # .v / .cst / .fs paths
  last_step,            # validate | build | program
  last_logs,            # captured stdout/stderr from last tool run
  last_verdict,         # VerifyAgent: pass | warn | fail + notes
  errors
}
```

## Proposed repo layout

```text
PLAN.md
README.md
boards.yaml               # supported boards registry (Tang Nano 9K only in v0)
pyproject.toml
.env.example
src/shepherd/
  __init__.py
  cli.py
  llm/client.py
  boards.py               # load/validate boards.yaml; allowlist helpers
  agents/
    base.py
    shepherd.py           # orchestrator + chat host
    guide.py              # natural language (NL) goal + clarifying questions
    design.py             # scaffold Verilog + constraints (.cst)
    env.py
    toolchain.py
    project.py
    build_program.py
    verify.py             # auto-check after validate/build/program
  tools/
    shell.py
    oss_cad.py
    project_fs.py
    fpga_build.py
    fpga_program.py
    board_tangnano9k.py   # pin / constraint helpers
    verify_logs.py        # parse/summarize toolchain + loader logs
  knowledge/
    tangnano9k.md         # board facts for Guide/Design prompts
  config.py
examples/button_led/      # minimal fixture + guided-flow demo target
docs/extending.md
```

## Core CLI flows

1. `shepherd chat` — **primary**: “How can we help you today?” → guide → scaffold → validate → **check** → build → **check** → program → **check**  
2. `shepherd doctor` — Env + Toolchain checklist  
3. `shepherd validate --project PATH` — then auto VerifyAgent (skip with `--no-check`)  
4. `shepherd build --project PATH` — then auto VerifyAgent  
5. `shepherd program --project PATH` — build + load (SRAM default; `--flash` optional) → auto VerifyAgent  
6. `shepherd check --stage … --project PATH` — VerifyAgent only  
7. `shepherd run --goal "..."` — non-interactive pipeline when goal + enough flags are provided  

## Build/program command skeleton

1. `yosys -p "read_verilog …; synth_gowin -top top -json out.json"`
2. `nextpnr-himbaechel` (or suite Gowin nextpnr) + device + `.cst`
3. `gowin_pack -d GW1N-9C -o design.fs …`
4. `openFPGALoader -b tangnano9k design.fs`

## Extensibility

- Stable **Tool** protocol: name, JSON schema, `run(**kwargs) -> ToolResult`
- Stable **Agent** protocol: `name`, `system_prompt`, `tools`, `run(goal, context) -> AgentResult`
- Later boards = new entry in `boards.yaml` + optional `knowledge/` + `board_*.py`
- Example stub in docs (e.g. `SimAgent` / UART listen)

## Out of scope for v0

- Boards other than Tang Nano 9K
- Driving Lushay Code UI / Computer Use
- Windows installer polish
- Fully autonomous hardware bring-up with no user confirmation on pin choices
- Cloud/Lushay cloud builds
- Guaranteeing every sensor datasheet is correct without user confirmation (GuideAgent must ask)

## Implementation order

1. Write / update **`PLAN.md`** (this document)
2. Scaffold Python package + CLI + Meta LLM client + `.env.example`
3. Add `boards.yaml` (Tang Nano 9K only) + `boards.py` loader; implement tools (shell, OSS CAD, project FS, build, program, board helpers, verify logs)
4. Implement specialists: Guide, Design, Env, Toolchain, Project, BuildProgram, **Verify** + Shepherd chat host (auto-check hooks; board allowlist from YAML)
5. Example project + `README.md` quickstart (include IMU-style guided example in docs)
6. Smoke-test: `chat` / `doctor` → `validate`+check → `build`+check; `program`+check when board connected

## Success criteria

- User can start `shepherd chat`, state a Tang Nano 9K goal in plain language, answer a few questions, and get a scaffolded + buildable project
- After validate/build/program, user always gets an AI verdict (`pass`/`warn`/`fail`) with concrete next steps — not just raw toolchain spam
- Teammate can clone, set Meta API key, run `shepherd doctor` and understand what’s missing
- Each agent runnable alone; full pipeline programs Tang Nano 9K when hardware + suite present
- Clear extension path for adding agents without rewriting the core loop
- Meta model usage is explicit and central

## Human toolchain reference (agents use CLI equivalents)

1. Optional editor extension (Lushay Code) for humans
2. OSS CAD Suite
3. Project with Verilog + `.cst`
4. Build and program (yosys → nextpnr → gowin_pack → openFPGALoader)
