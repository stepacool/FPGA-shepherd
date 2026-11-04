"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Props = {
  /** Absolute filesystem path to a .vcd / .fst / .ghw under the project. */
  filePath: string;
  project: string;
};

/**
 * Same-origin Surfer WASM at `/surfer/` (fetched by `npm run surfer`).
 * Falls back to the hosted app if the local build is missing.
 */
export function SurferEmbed({ filePath, project }: Props) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [ready, setReady] = useState(false);
  const [localSurfer, setLocalSurfer] = useState<boolean | null>(null);

  const artifactUrl = useMemo(() => {
    const u = new URL("/api/artifact", window.location.origin);
    u.searchParams.set("project", project);
    u.searchParams.set("path", filePath);
    return u.toString();
  }, [filePath, project]);

  const iframeSrc = useMemo(() => {
    if (localSurfer === null) return null;
    if (localSurfer) {
      return `/surfer/index.html?load_url=${encodeURIComponent(artifactUrl)}`;
    }
    return `https://app.surfer-project.org/?load_url=${encodeURIComponent(artifactUrl)}`;
  }, [localSurfer, artifactUrl]);

  useEffect(() => {
    let cancelled = false;
    fetch("/surfer/surfer_bg.wasm", { method: "HEAD" })
      .then((r) => {
        if (!cancelled) setLocalSurfer(r.ok);
      })
      .catch(() => {
        if (!cancelled) setLocalSurfer(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setReady(false);
  }, [artifactUrl, iframeSrc]);

  function postLoadUrl() {
    const win = iframeRef.current?.contentWindow;
    if (win) {
      win.postMessage({ command: "LoadUrl", url: artifactUrl }, "*");
    }
  }

  useEffect(() => {
    function onMessage(ev: MessageEvent) {
      if (ev.data?.type === "shepherd-surfer-ready") {
        setReady(true);
        postLoadUrl();
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- postLoadUrl closes over artifactUrl
  }, [artifactUrl]);

  if (!iframeSrc) {
    return (
      <p className="text-sm text-stone-500">Loading waveform viewer…</p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-xs text-stone-600">
        <span className="font-mono truncate" title={filePath}>
          {filePath}
        </span>
        <a
          className="underline hover:text-stone-900"
          href={iframeSrc}
          target="_blank"
          rel="noreferrer"
        >
          Open full screen
        </a>
        {!localSurfer && (
          <span className="text-amber-800">
            using hosted Surfer — run <code className="font-mono">npm run surfer</code> in{" "}
            <code className="font-mono">web/</code> for a local embed
          </span>
        )}
        {localSurfer && !ready && (
          <span className="text-stone-400">starting Surfer…</span>
        )}
      </div>
      <iframe
        ref={iframeRef}
        title="Surfer waveform"
        src={iframeSrc}
        className="h-[28rem] w-full rounded border border-stone-400 bg-stone-200"
        allow="fullscreen"
        onLoad={() => {
          // Query `load_url` usually works; retry LoadUrl after WASM boots.
          window.setTimeout(() => {
            setReady(true);
            postLoadUrl();
          }, 800);
        }}
      />
    </div>
  );
}
