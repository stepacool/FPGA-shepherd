"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { FolderPicker } from "@/components/FolderPicker";

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
  latest: RunRow | null;
  active: RunRow | null;
  lock: { locked: boolean; detail?: string };
  buildReady?: boolean;
  lastBuildOk?: RunRow | null;
};

const STEPS = ["adapter", "synth", "pnr", "pack", "upload", "verify"] as const;

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
  const [showBackend, setShowBackend] = useState(false);
  const [tab, setTab] = useState<"run" | "doctor" | "explain" | "ask" | "artifacts">(
    "run",
  );
  const [askQ, setAskQ] = useState("");
  const [askAnswer, setAskAnswer] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  /** True once this session sees a passing build (or API says bitstream/build exists). */
  const [buildReady, setBuildReady] = useState(false);
  const logEnd = useRef<HTMLDivElement>(null);
  const afterIdRef = useRef(0);

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
    setBuildReady(Boolean(data.buildReady));
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

  // Unlock upload/sim after a successful build in this session.
  useEffect(() => {
    if (run?.command === "build" && run.finished_at && run.verdict === "pass") {
      setBuildReady(true);
    }
  }, [run]);

  const stepState = useMemo(() => {
    const map = new Map<string, "pending" | "running" | "ok" | "fail">();
    for (const s of STEPS) map.set(s, "pending");
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

  const logLines = useMemo(
    () =>
      events.filter(
        (e) => e.kind === "log" || e.kind === "verdict" || e.kind === "ask",
      ),
    [events],
  );

  const artifacts = useMemo(() => {
    const rows: { message: string; path: string }[] = [];
    for (const e of events) {
      if (e.kind !== "artifact") continue;
      let path = "";
      try {
        path = JSON.parse(e.payload_json ?? "{}").path ?? "";
      } catch {
        path = "";
      }
      rows.push({ message: e.message ?? "artifact", path });
    }
    return rows;
  }, [events]);

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
    setBusy(true);
    setError(null);
    setAskAnswer(null);
    setEvents([]);
    afterIdRef.current = 0;
    const res = await fetch("/api/spawn", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ project, command, args, showBackend }),
    });
    const data = await res.json();
    setBusy(false);
    if (!data.ok) {
      setError(data.error ?? "spawn failed");
      return;
    }
    setRunId(data.runId);
    setRun({
      id: data.runId,
      command,
      board: info?.board ?? null,
      finished_at: null,
      verdict: null,
      started_at: new Date().toISOString(),
    });
    setTab(command === "doctor" ? "doctor" : command === "ask" ? "ask" : "run");
  }

  async function cancel() {
    if (!project || !runId) return;
    setBusy(true);
    const res = await fetch("/api/cancel", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ project, runId }),
    });
    const data = await res.json();
    setBusy(false);
    if (!data.ok) setError(data.error ?? "cancel failed");
  }

  async function submitAsk() {
    if (!askQ.trim()) return;
    await spawn("ask", [askQ.trim()]);
  }

  useEffect(() => {
    for (const e of events) {
      if (!e.payload_json) continue;
      try {
        const p = JSON.parse(e.payload_json);
        if (typeof p.answer === "string" && p.answer.trim()) {
          setAskAnswer(p.answer);
        }
      } catch {
        /* ignore */
      }
    }
  }, [events]);

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-4 px-4 py-6">
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
        {(
          [
            ["build", "Build", false],
            ["upload", "Upload", true],
            ["sim", "Sim", true],
            ["doctor", "Doctor", false],
            ["explain", "Explain", false],
          ] as const
        ).map(([cmd, label, needsBuild]) => {
          const blocked = needsBuild && !buildReady;
          return (
            <button
              key={cmd}
              type="button"
              disabled={!project || busy || blocked}
              title={
                blocked ? "Run Build successfully first" : undefined
              }
              className="rounded border border-stone-400 bg-white px-3 py-1.5 text-sm hover:bg-stone-100 disabled:opacity-40"
              onClick={() => void spawn(cmd)}
            >
              {label}
            </button>
          );
        })}
        <button
          type="button"
          disabled={!project || !runId || busy || !!run?.finished_at}
          className="rounded border border-red-400 bg-red-50 px-3 py-1.5 text-sm text-red-800 hover:bg-red-100 disabled:opacity-40"
          onClick={() => void cancel()}
        >
          Cancel
        </button>
        {!buildReady && project && (
          <span className="text-xs text-stone-500">
            Upload / Sim unlock after a successful Build
          </span>
        )}
      </section>

      <nav className="flex gap-1 border-b border-stone-300 text-sm">
        {(
          [
            ["run", "Run"],
            ["doctor", "Doctor"],
            ["explain", "Explain"],
            ["ask", "Ask"],
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
              const st = stepState.get(s) ?? "pending";
              const mark =
                st === "ok" ? "✓" : st === "fail" ? "✗" : st === "running" ? "●" : "·";
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
              className="rounded border border-stone-400 px-3 py-1.5 hover:bg-stone-100"
              disabled={!project || busy}
              onClick={() => void spawn("doctor")}
            >
              Run doctor
            </button>
            <button
              type="button"
              className="rounded border border-stone-400 px-3 py-1.5 hover:bg-stone-100"
              disabled={!project || busy}
              onClick={() => void spawn("doctor", ["--fix"])}
            >
              Fix
            </button>
          </div>
          <LogExcerpt lines={logLines} />
        </div>
      )}

      {tab === "explain" && (
        <div className="space-y-3 rounded border border-stone-300 bg-white p-4 text-sm">
          <button
            type="button"
            className="rounded border border-stone-400 px-3 py-1.5 hover:bg-stone-100"
            disabled={!project || busy}
            onClick={() => void spawn("explain")}
          >
            Explain last failure
          </button>
          {explainBits.length === 0 ? (
            <p className="text-stone-500">No verdict findings on this run yet.</p>
          ) : (
            explainBits.map((f, i) => (
              <div key={i} className="border-l-2 border-amber-700 pl-3">
                {f.cause && <p>cause: {f.cause}</p>}
                {f.fix && <p>fix: {f.fix}</p>}
                {!f.cause && f.message && <p>{f.message}</p>}
              </div>
            ))
          )}
        </div>
      )}

      {tab === "ask" && (
        <div className="space-y-3 rounded border border-stone-300 bg-white p-4 text-sm">
          <div className="flex gap-2">
            <input
              className="flex-1 rounded border border-stone-400 px-3 py-2"
              placeholder='e.g. why are the LEDs active-low?'
              value={askQ}
              onChange={(e) => setAskQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void submitAsk();
              }}
            />
            <button
              type="button"
              className="rounded bg-stone-900 px-3 py-2 text-stone-50 disabled:opacity-40"
              disabled={!project || busy || !askQ.trim()}
              onClick={() => void submitAsk()}
            >
              Ask
            </button>
          </div>
          {busy && !askAnswer && (
            <p className="text-stone-500">Waiting for answer (events on this run)…</p>
          )}
          {askAnswer ? (
            <div>
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-stone-500">
                Answer
              </p>
              <p className="whitespace-pre-wrap rounded border border-stone-200 bg-stone-50 p-3">
                {askAnswer}
              </p>
            </div>
          ) : (
            !busy && (
              <p className="text-stone-500">
                Answer appears here after Ask finishes (same run as in the Run tab).
              </p>
            )
          )}
        </div>
      )}

      {tab === "artifacts" && (
        <div className="rounded border border-stone-300 bg-white p-4 text-sm">
          {artifacts.length === 0 ? (
            <p className="text-stone-500">No artifact events on this run yet.</p>
          ) : (
            <ul className="space-y-1 font-mono text-xs">
              {artifacts.map((a, i) => (
                <li key={i}>
                  <span className="text-stone-500">{a.message}</span> {a.path}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
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
