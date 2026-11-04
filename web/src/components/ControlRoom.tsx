"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { FolderPicker } from "@/components/FolderPicker";
import { SurferEmbed } from "@/components/SurferEmbed";

type RunRow = {
  id: string;
  command: string;
  board: string | null;
  finished_at: string | null;
  verdict: string | null;
  started_at: string;
};

type EventRow = {
  id: number;
  kind: string;
  step: string | null;
  level: string | null;
  message: string | null;
  payload_json: string | null;
};

type ProjectInfo = {
  project: string;
  board: string | null;
  top: string | null;
  sources: string[];
  sourcesStamp?: number;
  latest: RunRow | null;
  active: RunRow | null;
  lock: { locked: boolean; detail?: string };
  buildReady?: boolean;
  lastBuildOk?: RunRow | null;
};

type StepStatus = "pending" | "running" | "ok" | "fail";

/** One Ask turn in the session scrollback (not persisted across reload). */
type AskTurn = { id: string; q: string; a: string | null };

const STEPS = ["adapter", "synth", "pnr", "pack", "upload", "verify"] as const;

function emptySteps(): Map<string, StepStatus> {
  const map = new Map<string, StepStatus>();
  for (const s of STEPS) map.set(s, "pending");
  return map;
}

function defaultProject(): string {
  if (typeof window === "undefined") return "";
  const q = new URLSearchParams(window.location.search).get("project");
  if (q) return q;
  // Demo default: blinky next to the repo (web/ is cwd for Next).
  return "";
}

export function ControlRoom() {
  const [projectInput, setProjectInput] = useState(defaultProject);
  const [project, setProject] = useState("");
  const [info, setInfo] = useState<ProjectInfo | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<RunRow | null>(null);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** Which command is in flight — drives button labels (“Asking…”) until the run finishes. */
  const [busyCmd, setBusyCmd] = useState<string | null>(null);
  const [showBackend, setShowBackend] = useState(false);
  const [tab, setTab] = useState<"run" | "doctor" | "explain" | "artifacts">("run");
  const [askQ, setAskQ] = useState("");
  /** Session-only Ask continuity (cleared on project change / Ask Clear). */
  const [askThread, setAskThread] = useState<AskTurn[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  /** Session gate: Upload unlocks only after a successful Build in this session. */
  const [built, setBuilt] = useState(false);
  /** Session gate: Verify unlocks only after a successful Upload in this session. */
  const [uploaded, setUploaded] = useState(false);
  /** Source mtime when Built flipped on — invalidate if sources change. */
  const [builtStamp, setBuiltStamp] = useState<number | null>(null);
  /** Sticky step strip across Build → Upload → Verify in this session. */
  const [flowSteps, setFlowSteps] = useState(() => emptySteps());
  const [wavePath, setWavePath] = useState<string | null>(null);
  /** Bump to remount Surfer when the user clicks View waveform again. */
  const [waveKey, setWaveKey] = useState(0);
  const logEnd = useRef<HTMLDivElement>(null);
  const askEnd = useRef<HTMLDivElement>(null);
  const waveSection = useRef<HTMLDivElement>(null);
  const afterIdRef = useRef(0);
  /** Only runs started from this UI session may flip Built / Uploaded. */
  const sessionSpawned = useRef(new Set<string>());

  const clearBuilt = useCallback(() => {
    setBuilt(false);
    setUploaded(false);
    setBuiltStamp(null);
  }, []);

  const loadProject = useCallback(async (path: string) => {
    setError(null);
    const res = await fetch(`/api/project?project=${encodeURIComponent(path)}`);
    const data = await res.json();
    if (!res.ok) {
      setError(data.error ?? "failed to load project");
      setInfo(null);
      return;
    }
    setInfo(data);
    setProject(path);
    // Built / Uploaded start off every time a project is opened.
    setBuilt(false);
    setUploaded(false);
    setBuiltStamp(null);
    setFlowSteps(emptySteps());
    sessionSpawned.current = new Set();
    setWavePath(null);
    setBusy(false);
    setBusyCmd(null);
    setAskThread([]);
    const follow = data.active?.id ?? data.latest?.id ?? null;
    setRunId(follow);
    setEvents([]);
    afterIdRef.current = 0;
    setRun(data.active ?? data.latest);
    const url = new URL(window.location.href);
    url.searchParams.set("project", path);
    window.history.replaceState({}, "", url);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (projectInput) {
        await loadProject(projectInput);
        return;
      }
      const res = await fetch("/api/defaults");
      const data = await res.json();
      if (cancelled || !data.blinky) return;
      setProjectInput(data.blinky);
      await loadProject(data.blinky);
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only default project
  }, []);

  useEffect(() => {
    if (!project || !runId) return;
    let cancelled = false;
    const tick = async () => {
      const res = await fetch(
        `/api/events?project=${encodeURIComponent(project)}&runId=${encodeURIComponent(runId)}&after=${afterIdRef.current}`,
      );
      const data = await res.json();
      if (cancelled || !res.ok) return;
      if (data.run) setRun(data.run);
      if (data.events?.length) {
        setEvents((prev) => [...prev, ...data.events]);
        afterIdRef.current = data.events[data.events.length - 1].id;
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 400);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [project, runId]);

  useEffect(() => {
    logEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  // Session Built / Uploaded from finished runs we spawned; clear on failure.
  useEffect(() => {
    if (!run?.finished_at || !run.verdict) return;
    if (!sessionSpawned.current.has(run.id)) return;
    if (run.command === "build") {
      if (run.verdict === "pass") {
        setBuilt(true);
        // Snapshot source mtimes at the moment Build passed.
        if (project) {
          void fetch(`/api/project?project=${encodeURIComponent(project)}`)
            .then((r) => r.json())
            .then((data) => {
              if (typeof data.sourcesStamp === "number") {
                setBuiltStamp(data.sourcesStamp);
                setInfo((prev) =>
                  prev ? { ...prev, sourcesStamp: data.sourcesStamp } : prev,
                );
              }
            })
            .catch(() => {
              /* non-fatal */
            });
        }
      } else {
        clearBuilt();
      }
    } else if (run.command === "upload") {
      if (run.verdict === "pass") {
        setUploaded(true);
      } else {
        setUploaded(false);
      }
    } else if (run.command === "wipe" && run.verdict === "pass") {
      setAskThread([]);
      setAskQ("");
      setEvents([]);
      afterIdRef.current = 0;
      sessionSpawned.current = new Set([run.id]);
    } else if (run.command === "ask" && run.finished_at && run.verdict === "fail") {
      setAskThread((prev) => {
        const i = prev.findLastIndex((t) => t.a === null);
        if (i < 0) return prev;
        const next = [...prev];
        next[i] = { ...next[i], a: "(no answer — see the run log)" };
        return next;
      });
    } else if (run.command === "reset" && run.verdict === "pass") {
      // FPGA SRAM cleared — upload gate resets until the next successful upload.
      setUploaded(false);
      setFlowSteps((prev) => {
        const next = new Map(prev);
        next.set("upload", "pending");
        next.set("verify", "pending");
        return next;
      });
    }
  }, [run, project, clearBuilt]);

  // Clear loading once the spawned Shepherd run finishes (or disappears).
  useEffect(() => {
    if (run?.finished_at) {
      setBusy(false);
      setBusyCmd(null);
    }
  }, [run?.finished_at]);

  // Unstick if Shepherd exited without ever writing this runId (e.g. early CLI error).
  useEffect(() => {
    if (!busy || !project || !runId || run?.finished_at) return;
    let cancelled = false;
    const started = Date.now();
    const tick = async () => {
      const res = await fetch(
        `/api/events?project=${encodeURIComponent(project)}&runId=${encodeURIComponent(runId)}&after=0`,
      );
      const data = await res.json();
      if (cancelled || !res.ok) return;
      if (data.run?.finished_at) {
        setRun(data.run);
        setBusy(false);
        setBusyCmd(null);
        return;
      }
      if (!data.run && Date.now() - started > 4000) {
        setBusy(false);
        setBusyCmd(null);
        setError(
          "Shepherd exited without finishing this run. Try again — Cancel should also free the UI.",
        );
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 1000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [busy, project, runId, run?.finished_at]);

  // Poll source mtimes; invalidate Built if HDL / toml changed after the build.
  useEffect(() => {
    if (!project || !built) return;
    let cancelled = false;
    const tick = async () => {
      const res = await fetch(`/api/project?project=${encodeURIComponent(project)}`);
      const data = await res.json();
      if (cancelled || !res.ok) return;
      if (typeof data.sourcesStamp === "number") {
        setInfo((prev) =>
          prev ? { ...prev, sourcesStamp: data.sourcesStamp } : prev,
        );
        if (builtStamp != null && data.sourcesStamp > builtStamp) {
          clearBuilt();
          setFlowSteps(emptySteps());
        }
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [project, built, builtStamp, clearBuilt]);

  const liveSteps = useMemo(() => {
    const map = emptySteps();
    for (const e of events) {
      if (!e.step) continue;
      if (e.kind === "step_start") map.set(e.step, "running");
      if (e.kind === "step_end") {
        let ok = e.level !== "error";
        try {
          const p = JSON.parse(e.payload_json ?? "{}");
          if (typeof p.ok === "boolean") ok = p.ok;
        } catch {
          /* keep level-based guess */
        }
        map.set(e.step, ok ? "ok" : "fail");
      }
      if (e.kind === "verdict" && e.step && e.level === "error") {
        map.set(e.step, "fail");
      }
    }
    return map;
  }, [events]);

  // Merge live step updates into the sticky Build → Upload → Verify strip.
  useEffect(() => {
    setFlowSteps((prev) => {
      let changed = false;
      const next = new Map(prev);
      for (const s of STEPS) {
        const st = liveSteps.get(s) ?? "pending";
        if (st !== "pending" && next.get(s) !== st) {
          next.set(s, st);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [liveSteps]);

  const logLines = useMemo(
    () =>
      events.filter(
        (e) => e.kind === "log" || e.kind === "verdict" || e.kind === "ask",
      ),
    [events],
  );

  const artifacts = useMemo(() => {
    const rows: { message: string; path: string; isWave: boolean }[] = [];
    for (const e of events) {
      if (e.kind !== "artifact") continue;
      let path = "";
      try {
        path = JSON.parse(e.payload_json ?? "{}").path ?? "";
      } catch {
        path = "";
      }
      const lower = path.toLowerCase();
      const isWave =
        lower.endsWith(".vcd") || lower.endsWith(".fst") || lower.endsWith(".ghw");
      rows.push({ message: e.message ?? "artifact", path, isWave });
    }
    return rows;
  }, [events]);

  const latestWave = useMemo(
    () => [...artifacts].reverse().find((a) => a.isWave)?.path ?? null,
    [artifacts],
  );

  useEffect(() => {
    if (latestWave && !wavePath) setWavePath(latestWave);
  }, [latestWave, wavePath]);

  const explainBits = useMemo(() => {
    const findings: { cause?: string; fix?: string; message?: string }[] = [];
    for (const e of events) {
      if (e.kind !== "verdict") continue;
      try {
        const payload = JSON.parse(e.payload_json ?? "{}");
        for (const f of payload.findings ?? []) findings.push(f);
      } catch {
        /* ignore */
      }
      if (e.message && e.level === "error") {
        findings.push({ message: e.message });
      }
    }
    return findings;
  }, [events]);

  async function spawn(command: string, args: string[] = []) {
    if (!project) {
      setError("open a project first");
      return;
    }
    const uiCmd =
      command === "ask" && args[0] === "wipe" ? "wipe" : command;
    setBusy(true);
    setBusyCmd(uiCmd);
    setError(null);
    if (command === "build") {
      // New build attempt: clear gates and the sticky strip until it passes.
      clearBuilt();
      setFlowSteps(emptySteps());
    } else if (command === "upload") {
      setUploaded(false);
      setFlowSteps((prev) => {
        const next = new Map(prev);
        next.set("upload", "pending");
        next.set("verify", "pending");
        return next;
      });
    } else if (command === "verify") {
      setFlowSteps((prev) => {
        const next = new Map(prev);
        next.set("verify", "pending");
        return next;
      });
    }
    setEvents([]);
    afterIdRef.current = 0;
    try {
      const res = await fetch("/api/spawn", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ project, command, args, showBackend }),
      });
      const data = await res.json();
      if (!data.ok) {
        setBusy(false);
        setBusyCmd(null);
        setError(data.error ?? "spawn failed");
        return;
      }
      sessionSpawned.current.add(data.runId);
      setRunId(data.runId);
      setRun({
        id: data.runId,
        command: uiCmd,
        board: info?.board ?? null,
        finished_at: null,
        verdict: null,
        started_at: new Date().toISOString(),
      });
      // Ask stays in the side rail — don't leave the current tool tab.
      if (command === "doctor" || command === "explain") {
        setTab(command);
      } else if (command === "sim") {
        setTab("artifacts");
      } else if (uiCmd !== "ask" && uiCmd !== "wipe") {
        setTab("run");
      }
    } catch (err) {
      setBusy(false);
      setBusyCmd(null);
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function cancel() {
    if (!project || !runId) return;
    setBusyCmd("cancel");
    try {
      const res = await fetch("/api/cancel", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ project, runId }),
      });
      const data = await res.json();
      if (!data.ok) {
        // Process already gone / never recorded — free the UI anyway.
        setBusy(false);
        setBusyCmd(null);
        setError(data.error ?? "cancel failed");
        setRun((prev) =>
          prev && !prev.finished_at
            ? { ...prev, finished_at: new Date().toISOString(), verdict: "fail" }
            : prev,
        );
        return;
      }
      // Stay busy until the run's finished_at arrives via events.
      setBusy(true);
    } catch (err) {
      setBusy(false);
      setBusyCmd(null);
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function submitAsk() {
    const q = askQ.trim();
    if (!q) return;
    setAskQ("");
    setAskThread((prev) => [
      ...prev,
      { id: `${Date.now()}-${prev.length}`, q, a: null },
    ]);
    await spawn("ask", [q]);
  }

  useEffect(() => {
    let answer: string | null = null;
    for (const e of events) {
      if (!e.payload_json) continue;
      try {
        const p = JSON.parse(e.payload_json);
        if (typeof p.answer === "string" && p.answer.trim()) {
          answer = p.answer;
        }
      } catch {
        /* ignore */
      }
    }
    if (!answer) return;
    setAskThread((prev) => {
      const i = prev.findLastIndex((t) => t.a === null);
      if (i < 0) return prev;
      const next = [...prev];
      next[i] = { ...next[i], a: answer };
      return next;
    });
  }, [events]);

  useEffect(() => {
    askEnd.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [askThread, busyCmd]);

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-4 px-4 py-6">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-stone-300 pb-4">
        <div>
          <p className="font-display text-2xl tracking-tight text-stone-900">
            Shepherd
          </p>
          <p className="text-sm text-stone-600">
            Live run view — same SQLite events as the CLI. No separate job API.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-stone-700">
          <input
            type="checkbox"
            checked={showBackend}
            onChange={(e) => setShowBackend(e.target.checked)}
          />
          Advanced: show backend commands
        </label>
      </header>

      <section className="flex flex-wrap items-center gap-2">
        <input
          className="min-w-[20rem] flex-1 rounded border border-stone-400 bg-white px-3 py-2 font-mono text-sm"
          placeholder="/absolute/path/to/project"
          value={projectInput}
          onChange={(e) => setProjectInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void loadProject(projectInput.trim());
          }}
        />
        <button
          type="button"
          className="rounded border border-stone-400 bg-white px-3 py-2 text-sm hover:bg-stone-100"
          onClick={() => setPickerOpen(true)}
        >
          Browse…
        </button>
        <button
          type="button"
          className="rounded bg-stone-900 px-3 py-2 text-sm text-stone-50 hover:bg-stone-700"
          onClick={() => void loadProject(projectInput.trim())}
        >
          Open
        </button>
      </section>

      {pickerOpen && (
        <FolderPicker
          initialPath={projectInput || project || undefined}
          onCancel={() => setPickerOpen(false)}
          onOk={(path) => {
            setPickerOpen(false);
            setProjectInput(path);
            void loadProject(path);
          }}
        />
      )}

      {info && (
        <section className="grid gap-2 rounded border border-stone-300 bg-stone-50 px-3 py-2 text-sm sm:grid-cols-4">
          <div>
            <span className="text-stone-500">board</span>{" "}
            <span className="font-mono">{info.board ?? "—"}</span>
          </div>
          <div>
            <span className="text-stone-500">top</span>{" "}
            <span className="font-mono">{info.top ?? "—"}</span>
          </div>
          <div>
            <span className="text-stone-500">verdict</span>{" "}
            <VerdictBadge verdict={run?.verdict ?? info.latest?.verdict} />
          </div>
          <div className="truncate font-mono text-stone-600" title={info.project}>
            {info.project}
          </div>
        </section>
      )}

      {error && (
        <p className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      )}

      <section className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {(
            [
              ["build", "Build", false, false],
              ["upload", "Upload", true, false],
              ["verify", "Verify", false, true],
            ] as const
          ).map(([cmd, label, needsBuilt, needsUploaded]) => {
            const blocked =
              (needsBuilt && !built) || (needsUploaded && !uploaded);
            const loading = busyCmd === cmd;
            const title = needsUploaded && !uploaded
              ? "Run Upload successfully first"
              : needsBuilt && !built
                ? "Run Build successfully first"
                : undefined;
            return (
              <button
                key={cmd}
                type="button"
                disabled={!project || busy || blocked}
                aria-busy={loading}
                title={title}
                className="rounded border border-stone-400 bg-white px-3 py-1.5 text-sm hover:bg-stone-100 disabled:opacity-40"
                onClick={() => void spawn(cmd)}
              >
                {loading ? `${BUSY_LABEL[cmd] ?? "Working"}…` : label}
              </button>
            );
          })}
          {project && (!built || !uploaded) && (
            <span className="text-xs text-stone-500">
              {!built
                ? "Upload unlocks after a successful Build"
                : "Verify unlocks after a successful Upload"}
            </span>
          )}
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={!project || busy || !built}
            aria-busy={busyCmd === "sim"}
            title={!built ? "Run Build successfully first" : undefined}
            className="rounded border border-stone-400 bg-white px-3 py-1.5 text-sm hover:bg-stone-100 disabled:opacity-40"
            onClick={() => void spawn("sim")}
          >
            {busyCmd === "sim" ? "Simulating…" : "Sim"}
          </button>
          <button
            type="button"
            disabled={!project || busy}
            aria-busy={busyCmd === "reset"}
            title="Reset the FPGA (clear SRAM program)"
            className="rounded border border-stone-400 bg-white px-3 py-1.5 text-sm hover:bg-stone-100 disabled:opacity-40"
            onClick={() => void spawn("reset")}
          >
            {busyCmd === "reset" ? "Resetting…" : "Reset"}
          </button>
          <button
            type="button"
            disabled={
              !project ||
              !runId ||
              !!run?.finished_at ||
              busyCmd === "cancel"
            }
            aria-busy={busyCmd === "cancel"}
            title={
              run?.finished_at
                ? "Nothing to cancel"
                : "Stop the current Shepherd run / unstick the UI"
            }
            className="rounded border border-red-400 bg-red-50 px-3 py-1.5 text-sm text-red-800 hover:bg-red-100 disabled:opacity-40"
            onClick={() => void cancel()}
          >
            {busyCmd === "cancel" ? "Cancelling…" : "Cancel"}
          </button>
        </div>
      </section>

      <div className="grid flex-1 gap-4 lg:grid-cols-[1fr_20rem] lg:items-start">
        <div className="min-w-0 space-y-4">
          <nav className="flex gap-1 border-b border-stone-300 text-sm">
            {(
              [
                ["run", "Run"],
                ["doctor", "Doctor"],
                ["explain", "Explain"],
                ["artifacts", "Artifacts"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={`px-3 py-2 ${
                  tab === id
                    ? "border-b-2 border-amber-700 font-medium text-stone-900"
                    : "text-stone-500"
                }`}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>

          {tab === "run" && (
            <div className="grid gap-4 md:grid-cols-[14rem_1fr]">
              <ol className="space-y-1 rounded border border-stone-300 bg-white p-3 text-sm">
                {STEPS.map((s) => {
                  const st = flowSteps.get(s) ?? "pending";
                  const mark =
                    st === "ok"
                      ? "✓"
                      : st === "fail"
                        ? "✗"
                        : st === "running"
                          ? "●"
                          : "·";
                  const color =
                    st === "ok"
                      ? "text-emerald-700"
                      : st === "fail"
                        ? "text-red-700"
                        : st === "running"
                          ? "text-amber-700"
                          : "text-stone-400";
                  return (
                    <li key={s} className={`font-mono ${color}`}>
                      <span className="inline-block w-4">{mark}</span> {s}
                    </li>
                  );
                })}
                <li className="pt-2 text-xs text-stone-500">
                  run {runId ? <span className="font-mono">{runId}</span> : "—"}
                </li>
              </ol>
              <div className="flex max-h-[28rem] flex-col rounded border border-stone-300 bg-stone-950 p-3 font-mono text-xs text-stone-100">
                <div className="mb-2 text-stone-400">log</div>
                <div className="flex-1 overflow-y-auto">
                  {logLines.map((e) => (
                    <div
                      key={e.id}
                      className={
                        e.level === "error"
                          ? "text-red-300"
                          : e.level === "warn"
                            ? "text-amber-200"
                            : "text-stone-200"
                      }
                    >
                      {e.step ? `[${e.step}] ` : ""}
                      {e.message}
                    </div>
                  ))}
                  <div ref={logEnd} />
                </div>
              </div>
            </div>
          )}

          {tab === "doctor" && (
            <div className="rounded border border-stone-300 bg-white p-4 text-sm">
              <p className="mb-2 text-stone-600">
                Spawn <code className="font-mono">shepherd doctor</code> (or Fix with{" "}
                <code className="font-mono">--fix</code>). Checklist lines appear in the
                event log.
              </p>
              <div className="mb-3 flex gap-2">
                <button
                  type="button"
                  className="rounded border border-stone-400 px-3 py-1.5 hover:bg-stone-100 disabled:opacity-40"
                  disabled={!project || busy}
                  aria-busy={busyCmd === "doctor"}
                  onClick={() => void spawn("doctor")}
                >
                  {busyCmd === "doctor" ? "Running…" : "Run doctor"}
                </button>
                <button
                  type="button"
                  className="rounded border border-stone-400 px-3 py-1.5 hover:bg-stone-100 disabled:opacity-40"
                  disabled={!project || busy}
                  onClick={() => void spawn("doctor", ["--fix"])}
                >
                  {busyCmd === "doctor" ? "Fixing…" : "Fix"}
                </button>
              </div>
              <LogExcerpt lines={logLines} />
            </div>
          )}

          {tab === "explain" && (
            <div className="space-y-3 rounded border border-stone-300 bg-white p-4 text-sm">
              <button
                type="button"
                className="rounded border border-stone-400 px-3 py-1.5 hover:bg-stone-100 disabled:opacity-40"
                disabled={!project || busy}
                aria-busy={busyCmd === "explain"}
                onClick={() => void spawn("explain")}
              >
                {busyCmd === "explain" ? "Explaining…" : "Explain last failure"}
              </button>
              {explainBits.length === 0 ? (
                <p className="text-stone-500">No verdict findings on this run yet.</p>
              ) : (
                explainBits.map((f, i) => (
                  <div
                    key={i}
                    className="border-l-2 border-amber-700 pl-3 leading-relaxed"
                  >
                    {f.cause && (
                      <p>
                        cause: <InlineMarkdown text={f.cause} />
                      </p>
                    )}
                    {f.fix && (
                      <p>
                        fix: <InlineMarkdown text={f.fix} />
                      </p>
                    )}
                    {!f.cause && f.message && (
                      <p>
                        <InlineMarkdown text={f.message} />
                      </p>
                    )}
                  </div>
                ))
              )}
            </div>
          )}

          {tab === "artifacts" && (
            <div className="space-y-4 rounded border border-stone-300 bg-white p-4 text-sm">
              <p className="text-stone-600">
                Files produced by runs (bitstream from Build,{" "}
                <code className="font-mono">.vcd</code> from Sim, etc.). Sim is the
                command; this tab lists what it wrote.
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={!project || busy || !built}
                  aria-busy={busyCmd === "sim"}
                  title={!built ? "Run Build successfully first" : undefined}
                  className="rounded border border-stone-400 bg-white px-3 py-1.5 text-sm hover:bg-stone-100 disabled:opacity-40"
                  onClick={() => void spawn("sim")}
                >
                  {busyCmd === "sim" ? "Simulating…" : "Sim"}
                </button>
                <span className="text-xs text-stone-500">
                  Runs <code className="font-mono">shepherd sim</code> — waveform appears
                  below when a VCD path is emitted.
                </span>
              </div>
              {artifacts.length === 0 ? (
                <p className="text-stone-500">No artifact events on this run yet.</p>
              ) : (
                <ul className="space-y-1 font-mono text-xs">
                  {artifacts.map((a, i) => (
                    <li key={i} className="flex flex-wrap items-baseline gap-2">
                      <span className="text-stone-500">{a.message}</span>
                      <span className="break-all">{a.path}</span>
                      {a.isWave && (
                        <button
                          type="button"
                          className="rounded border border-amber-700/40 bg-amber-50 px-2 py-0.5 text-[11px] text-amber-900 hover:bg-amber-100"
                          onClick={() => {
                            setWavePath(a.path);
                            setWaveKey((k) => k + 1);
                            requestAnimationFrame(() => {
                              waveSection.current?.scrollIntoView({
                                behavior: "smooth",
                                block: "nearest",
                              });
                            });
                          }}
                        >
                          View waveform
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {project && wavePath && (
                <div
                  ref={waveSection}
                  className="border-t border-stone-200 pt-3"
                >
                  <p className="mb-2 font-medium text-stone-800">Waveform (Surfer)</p>
                  <SurferEmbed
                    key={`${wavePath}:${waveKey}`}
                    project={project}
                    filePath={wavePath}
                  />
                </div>
              )}
            </div>
          )}
        </div>

        <aside className="flex min-h-[22rem] flex-col rounded border border-stone-300 bg-white lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)]">
          <div className="flex items-start gap-2 border-b border-stone-200 px-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="font-medium text-stone-900">Ask</p>
              <p className="text-xs text-stone-500">
                About this project or any part of the build, upload or simulation
              </p>
            </div>
            <button
              type="button"
              disabled={!project || busy || askThread.length === 0}
              aria-busy={busyCmd === "wipe"}
              title="Wipe Ask thread and run history"
              className="shrink-0 rounded border border-stone-300 px-2 py-1 text-xs text-stone-600 hover:bg-stone-100 disabled:opacity-40"
              onClick={() => void spawn("ask", ["wipe"])}
            >
              {busyCmd === "wipe" ? "Wiping…" : "Clear"}
            </button>
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 text-sm">
            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
              {askThread.length === 0 && busyCmd !== "ask" && (
                <p className="text-stone-500">
                  Ask anything about the board, RTL, or the last run. Questions in
                  this session stay here until Clear.
                </p>
              )}
              {askThread.map((turn) => (
                <div key={turn.id} className="space-y-2">
                  <div>
                    <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-stone-500">
                      You
                    </p>
                    <p className="rounded bg-stone-100 px-2 py-1.5 text-stone-800">
                      {turn.q}
                    </p>
                  </div>
                  <div>
                    <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-stone-500">
                      Shepherd
                    </p>
                    {turn.a == null ? (
                      <p className="text-stone-500">Waiting for answer…</p>
                    ) : (
                      <div className="whitespace-pre-wrap rounded border border-stone-200 bg-stone-50 px-2 py-1.5 leading-relaxed text-stone-900">
                        <InlineMarkdown text={turn.a} />
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <div ref={askEnd} />
            </div>
            <div className="flex gap-2 border-t border-stone-100 pt-3">
              <input
                className="min-w-0 flex-1 rounded border border-stone-400 px-2 py-1.5 text-sm"
                placeholder="e.g. why are the LEDs active-low?"
                value={askQ}
                disabled={!project || busy}
                onChange={(e) => setAskQ(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void submitAsk();
                }}
              />
              <button
                type="button"
                className="shrink-0 rounded bg-stone-900 px-3 py-1.5 text-sm text-stone-50 disabled:opacity-40"
                disabled={!project || busy || !askQ.trim()}
                aria-busy={busyCmd === "ask"}
                onClick={() => void submitAsk()}
              >
                {busyCmd === "ask" ? "Asking…" : "Ask"}
              </button>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

const BUSY_LABEL: Record<string, string> = {
  build: "Building",
  upload: "Uploading",
  verify: "Verifying",
  reset: "Resetting",
  wipe: "Wiping",
  sim: "Simulating",
  doctor: "Running",
  explain: "Explaining",
  ask: "Asking",
  cancel: "Cancelling",
};

const CODE_CLASS =
  "rounded bg-stone-200/80 px-1 py-0.5 font-mono text-[0.9em] text-stone-900";

/**
 * Light formatting for ask/explain answers:
 * - `backtick code`
 * - 'identifier' (no spaces; avoids don't / it's)
 * - **bold**
 */
function InlineMarkdown({ text }: { text: string }) {
  const parts = text.split(
    /(`[^`]+`|\*\*[^*]+\*\*|'[A-Za-z_][\w.$-]{0,62}')/g,
  );
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("`") && part.endsWith("`") && part.length >= 2) {
          return (
            <code key={i} className={CODE_CLASS}>
              {part.slice(1, -1)}
            </code>
          );
        }
        if (
          part.startsWith("'") &&
          part.endsWith("'") &&
          part.length >= 3 &&
          !part.slice(1, -1).includes(" ")
        ) {
          return (
            <code key={i} className={CODE_CLASS}>
              {part.slice(1, -1)}
            </code>
          );
        }
        if (part.startsWith("**") && part.endsWith("**") && part.length >= 4) {
          return (
            <strong key={i} className="font-semibold text-stone-900">
              {part.slice(2, -2)}
            </strong>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

function VerdictBadge({ verdict }: { verdict: string | null | undefined }) {
  if (!verdict) return <span className="text-stone-400">—</span>;
  const color =
    verdict === "pass"
      ? "text-emerald-700"
      : verdict === "warn"
        ? "text-amber-700"
        : "text-red-700";
  return <span className={`font-semibold uppercase ${color}`}>{verdict}</span>;
}

function LogExcerpt({ lines }: { lines: EventRow[] }) {
  return (
    <div className="max-h-64 overflow-y-auto rounded bg-stone-950 p-3 font-mono text-xs text-stone-200">
      {lines.length === 0 && <span className="text-stone-500">no log lines yet</span>}
      {lines.map((e) => (
        <div key={e.id}>{e.message}</div>
      ))}
    </div>
  );
}
