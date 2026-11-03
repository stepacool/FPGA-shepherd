"use client";

import { useCallback, useEffect, useState } from "react";

type DirEntry = {
  name: string;
  path: string;
  hasShepherdToml: boolean;
};

type BrowsePayload = {
  path: string;
  parent: string | null;
  home: string;
  repo: string;
  entries: DirEntry[];
  error?: string;
};

type Props = {
  initialPath?: string;
  onOk: (path: string) => void;
  onCancel: () => void;
};

export function FolderPicker({ initialPath, onOk, onCancel }: Props) {
  const [data, setData] = useState<BrowsePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(async (dir?: string) => {
    setLoading(true);
    setError(null);
    setSelected(null);
    const q = dir ? `?path=${encodeURIComponent(dir)}` : "";
    const res = await fetch(`/api/browse${q}`);
    const body = (await res.json()) as BrowsePayload;
    setLoading(false);
    if (!res.ok) {
      setError(body.error ?? "could not list folder");
      return;
    }
    setData(body);
    setSelected(body.path);
  }, []);

  useEffect(() => {
    void load(initialPath || undefined);
  }, [initialPath, load]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-stone-900/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Choose project folder"
    >
      <div className="flex max-h-[min(36rem,90vh)] w-full max-w-xl flex-col rounded-lg border border-stone-400 bg-stone-50 shadow-lg">
        <header className="border-b border-stone-300 px-4 py-3">
          <p className="font-medium text-stone-900">Choose project folder</p>
          <p className="truncate font-mono text-xs text-stone-600" title={data?.path}>
            {data?.path ?? "…"}
          </p>
        </header>

        <div className="flex flex-wrap gap-2 border-b border-stone-200 px-4 py-2 text-xs">
          <button
            type="button"
            className="rounded border border-stone-400 bg-white px-2 py-1 hover:bg-stone-100 disabled:opacity-40"
            disabled={!data?.parent || loading}
            onClick={() => data?.parent && void load(data.parent)}
          >
            ↑ Up
          </button>
          <button
            type="button"
            className="rounded border border-stone-400 bg-white px-2 py-1 hover:bg-stone-100 disabled:opacity-40"
            disabled={loading || !data?.home}
            onClick={() => data && void load(data.home)}
          >
            Home
          </button>
          <button
            type="button"
            className="rounded border border-stone-400 bg-white px-2 py-1 hover:bg-stone-100 disabled:opacity-40"
            disabled={loading || !data?.repo}
            onClick={() => data && void load(data.repo)}
          >
            Repo
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
          {loading && <p className="px-2 text-sm text-stone-500">Loading…</p>}
          {error && <p className="px-2 text-sm text-red-700">{error}</p>}
          {!loading && data && data.entries.length === 0 && (
            <p className="px-2 text-sm text-stone-500">No subfolders here.</p>
          )}
          <ul className="space-y-0.5">
            {data?.entries.map((e) => {
              const active = selected === e.path;
              return (
                <li key={e.path}>
                  <button
                    type="button"
                    className={`flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-sm hover:bg-stone-200 ${
                      active ? "bg-amber-100 ring-1 ring-amber-700" : ""
                    }`}
                    onClick={() => setSelected(e.path)}
                    onDoubleClick={() => void load(e.path)}
                  >
                    <span className="font-mono">{e.name}/</span>
                    {e.hasShepherdToml && (
                      <span className="rounded bg-emerald-100 px-1.5 text-[10px] font-medium uppercase text-emerald-800">
                        shepherd
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="mt-2 px-2 text-[11px] text-stone-500">
            Double-click a folder to open it. Select a folder, then OK.
          </p>
        </div>

        <footer className="flex justify-end gap-2 border-t border-stone-300 px-4 py-3">
          <button
            type="button"
            className="rounded border border-stone-400 bg-white px-3 py-1.5 text-sm hover:bg-stone-100"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            className="rounded bg-stone-900 px-3 py-1.5 text-sm text-stone-50 hover:bg-stone-700 disabled:opacity-40"
            disabled={!selected}
            onClick={() => selected && onOk(selected)}
          >
            OK
          </button>
        </footer>
      </div>
    </div>
  );
}
