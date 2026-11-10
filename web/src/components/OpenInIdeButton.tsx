"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type EditorOption = { id: string; label: string };

type Props = {
  project: string;
  disabled?: boolean;
};

const STORAGE_KEY = "shepherd.ui.editorId";

export function OpenInIdeButton({ project, disabled }: Props) {
  const [editors, setEditors] = useState<EditorOption[]>([]);
  const [defaultId, setDefaultId] = useState<string>("file-manager");
  const [preferred, setPreferred] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/editors");
        const data = await res.json();
        if (cancelled || !res.ok) return;
        setEditors(data.available ?? []);
        setDefaultId(data.defaultId ?? "file-manager");
      } catch {
        /* ignore */
      }
    })();
    try {
      setPreferred(window.localStorage.getItem(STORAGE_KEY));
    } catch {
      setPreferred(null);
    }
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menuOpen]);

  const activeId =
    (preferred && editors.some((e) => e.id === preferred) ? preferred : null) ??
    defaultId;
  const activeLabel =
    editors.find((e) => e.id === activeId)?.label ?? "File manager";
  const hasIdeCli = editors.some((e) => e.id !== "file-manager");

  const openWith = useCallback(
    async (editorId: string) => {
      setError(null);
      setMenuOpen(false);
      try {
        window.localStorage.setItem(STORAGE_KEY, editorId);
      } catch {
        /* ignore */
      }
      setPreferred(editorId);
      const res = await fetch("/api/open-ide", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ project, editorId }),
      });
      const data = await res.json();
      if (!data.ok) {
        setError(data.error ?? "could not open editor");
      }
    },
    [project],
  );

  async function copyPath() {
    setMenuOpen(false);
    try {
      await navigator.clipboard.writeText(project);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("could not copy path");
    }
  }

  return (
    <div ref={rootRef} className="relative flex items-center gap-1">
      <button
        type="button"
        className="inline-flex items-center gap-1.5 rounded border border-stone-400 bg-white px-3 py-2 text-sm hover:bg-stone-100 disabled:opacity-40"
        disabled={disabled || !project}
        title={`Open in ${activeLabel}`}
        onClick={() => void openWith(activeId)}
      >
        <span aria-hidden className="text-base leading-none">
          ⌨
        </span>
        <span>IDE</span>
        <span aria-hidden className="text-stone-500">
          ↗
        </span>
      </button>
      <button
        type="button"
        className="rounded border border-stone-400 bg-white px-2 py-2 text-sm hover:bg-stone-100 disabled:opacity-40"
        disabled={disabled || !project}
        aria-label="Choose editor"
        aria-expanded={menuOpen}
        onClick={() => setMenuOpen((v) => !v)}
      >
        ▾
      </button>

      {menuOpen && (
        <div className="absolute right-0 top-full z-40 mt-1 min-w-[12rem] rounded border border-stone-400 bg-white py-1 shadow-lg">
          {!hasIdeCli && (
            <p className="px-3 py-1.5 text-xs text-amber-800">
              No editor CLI found — using file manager.
            </p>
          )}
          {editors.map((e) => (
            <button
              key={e.id}
              type="button"
              className={`flex w-full items-center justify-between px-3 py-1.5 text-left text-sm hover:bg-stone-100 ${
                e.id === activeId ? "bg-amber-50 font-medium" : ""
              }`}
              onClick={() => void openWith(e.id)}
            >
              <span>{e.label}</span>
              {e.id === activeId && <span className="text-xs text-stone-500">default</span>}
            </button>
          ))}
          <div className="my-1 border-t border-stone-200" />
          <button
            type="button"
            className="flex w-full px-3 py-1.5 text-left text-sm hover:bg-stone-100"
            onClick={() => void copyPath()}
          >
            {copied ? "Copied path" : "Copy path"}
          </button>
        </div>
      )}

      {error && (
        <span className="absolute left-0 top-full mt-1 whitespace-nowrap text-xs text-red-700">
          {error}
        </span>
      )}
    </div>
  );
}
