"use client";

import { useMemo, useState } from "react";

import { FolderPicker } from "@/components/FolderPicker";

type Props = {
  initialParent?: string;
  showBackend?: boolean;
  onCreated: (project: string, runId: string) => void;
  onCancel: () => void;
};

function joinPreview(parent: string, name: string): string {
  if (!parent) return name ? `…/${name}` : "";
  const sep = parent.endsWith("/") ? "" : "/";
  return name ? `${parent}${sep}${name}` : parent;
}

export function InitProjectModal({
  initialParent,
  showBackend,
  onCreated,
  onCancel,
}: Props) {
  const [name, setName] = useState("");
  const [parent, setParent] = useState(initialParent ?? "");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const preview = useMemo(() => joinPreview(parent, name.trim()), [parent, name]);

  async function create() {
    setError(null);
    const trimmed = name.trim();
    if (!trimmed) {
      setError("enter a project name");
      return;
    }
    if (/\s/.test(trimmed)) {
      setError("project name cannot contain spaces — use hyphens or underscores");
      return;
    }
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(trimmed)) {
      setError(
        "use letters, digits, ., _, - only (no spaces; must start with a letter or digit)",
      );
      return;
    }
    if (!parent.trim()) {
      setError("choose a parent folder");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/init", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          parent: parent.trim(),
          name: trimmed,
          showBackend,
        }),
      });
      const data = await res.json();
      if (!data.ok) {
        setBusy(false);
        setError(data.error ?? "init failed");
        return;
      }

      // init does not write UI event rows — wait until shepherd.toml exists.
      const project = data.project as string;
      const deadline = Date.now() + 120_000;
      while (Date.now() < deadline) {
        const probe = await fetch(
          `/api/project?project=${encodeURIComponent(project)}`,
        );
        if (probe.ok) {
          setBusy(false);
          onCreated(project, data.runId as string);
          return;
        }
        await new Promise((r) => setTimeout(r, 500));
      }
      setBusy(false);
      setError(
        `init is taking too long — check ${project} and retry Open if shepherd.toml appeared`,
      );
    } catch (err) {
      setBusy(false);
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <>
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-stone-900/40 p-4"
        role="dialog"
        aria-modal="true"
        aria-label="Initialize new project"
      >
        <div className="w-full max-w-lg rounded-lg border border-stone-400 bg-stone-50 shadow-lg">
          <header className="border-b border-stone-300 px-4 py-3">
            <p className="font-medium text-stone-900">Initialize new project</p>
            <p className="text-xs text-stone-600">
              Creates a folder, writes a Tang Nano 9K starter skeleton, and runs{" "}
              <code className="font-mono">shepherd init --yes</code>.
            </p>
          </header>

          <div className="space-y-3 px-4 py-4">
            <label className="block text-sm">
              <span className="text-stone-600">Project name</span>
              <input
                className="mt-1 w-full rounded border border-stone-400 bg-white px-3 py-2 font-mono text-sm"
                value={name}
                onChange={(e) => setName(e.target.value.replace(/\s+/g, "-"))}
                placeholder="my-fpga-project"
                disabled={busy}
                autoFocus
                spellCheck={false}
                autoComplete="off"
              />
              <span className="mt-1 block text-xs text-stone-500">
                No spaces — letters, digits, <code className="font-mono">.</code>{" "}
                <code className="font-mono">_</code> <code className="font-mono">-</code> only.
              </span>
            </label>

            <label className="block text-sm">
              <span className="text-stone-600">Parent folder</span>
              <div className="mt-1 flex gap-2">
                <input
                  className="min-w-0 flex-1 rounded border border-stone-400 bg-white px-3 py-2 font-mono text-sm"
                  value={parent}
                  onChange={(e) => setParent(e.target.value)}
                  placeholder="/home/you/projects"
                  disabled={busy}
                />
                <button
                  type="button"
                  className="shrink-0 rounded border border-stone-400 bg-white px-3 py-2 text-sm hover:bg-stone-100 disabled:opacity-40"
                  disabled={busy}
                  onClick={() => setPickerOpen(true)}
                >
                  Browse…
                </button>
              </div>
            </label>

            {preview && (
              <p className="truncate font-mono text-xs text-stone-600" title={preview}>
                Will create: {preview}
              </p>
            )}

            {error && <p className="text-sm text-red-700">{error}</p>}
            {busy && (
              <p className="text-sm text-stone-600">Initializing… (scaffold + toolchain)</p>
            )}
          </div>

          <footer className="flex justify-end gap-2 border-t border-stone-300 px-4 py-3">
            <button
              type="button"
              className="rounded border border-stone-400 bg-white px-3 py-1.5 text-sm hover:bg-stone-100 disabled:opacity-40"
              disabled={busy}
              onClick={onCancel}
            >
              Cancel
            </button>
            <button
              type="button"
              className="rounded bg-stone-900 px-3 py-1.5 text-sm text-stone-50 hover:bg-stone-700 disabled:opacity-40"
              disabled={busy}
              onClick={() => void create()}
            >
              {busy ? "Creating…" : "Create"}
            </button>
          </footer>
        </div>
      </div>

      {pickerOpen && (
        <FolderPicker
          initialPath={parent || undefined}
          requireShepherdToml={false}
          title="Choose parent folder"
          onCancel={() => setPickerOpen(false)}
          onOk={(path) => {
            setParent(path);
            setPickerOpen(false);
          }}
        />
      )}
    </>
  );
}
