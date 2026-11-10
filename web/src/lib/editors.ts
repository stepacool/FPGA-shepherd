import "server-only";

import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export type EditorId = "cursor" | "code" | "codium" | "file-manager";

export type EditorInfo = {
  id: EditorId;
  label: string;
  command: string;
  args: string[];
};

const EDITOR_CANDIDATES: {
  id: Exclude<EditorId, "file-manager">;
  label: string;
  binaries: string[];
}[] = [
  { id: "cursor", label: "Cursor", binaries: ["cursor"] },
  { id: "code", label: "VS Code", binaries: ["code"] },
  { id: "codium", label: "VSCodium", binaries: ["codium"] },
];

function which(bin: string): string | null {
  const result = spawnSync("which", [bin], { encoding: "utf8" });
  if (result.status !== 0) return null;
  const found = (result.stdout || "").trim().split("\n")[0];
  return found || null;
}

function fileManager(): EditorInfo {
  const platform = os.platform();
  if (platform === "darwin") {
    return { id: "file-manager", label: "Finder", command: "open", args: [] };
  }
  if (platform === "win32") {
    return {
      id: "file-manager",
      label: "File Explorer",
      command: "explorer",
      args: [],
    };
  }
  return {
    id: "file-manager",
    label: "File manager",
    command: "xdg-open",
    args: [],
  };
}

/** Detect installed editor CLIs plus a always-available file-manager fallback. */
export function listEditors(): { available: EditorInfo[]; defaultId: EditorId } {
  const available: EditorInfo[] = [];
  for (const cand of EDITOR_CANDIDATES) {
    for (const bin of cand.binaries) {
      const command = which(bin);
      if (command) {
        available.push({
          id: cand.id,
          label: cand.label,
          command,
          args: [],
        });
        break;
      }
    }
  }
  available.push(fileManager());
  const defaultId = available[0]?.id ?? "file-manager";
  return { available, defaultId };
}

export function resolveEditor(
  editorId: string | undefined,
): EditorInfo | null {
  const { available, defaultId } = listEditors();
  const id = (editorId?.trim() || defaultId) as EditorId;
  return available.find((e) => e.id === id) ?? available[0] ?? null;
}

/**
 * Open `projectPath` in the chosen editor / file manager.
 * Project folder must exist; prefer Shepherd projects.
 */
export function openInEditor(
  projectPath: string,
  editorId?: string,
): { ok: true; editor: EditorInfo } | { ok: false; error: string } {
  const abs = path.resolve(projectPath);
  if (!fs.existsSync(abs) || !fs.statSync(abs).isDirectory()) {
    return { ok: false, error: `project folder not found: ${abs}` };
  }

  const editor = resolveEditor(editorId);
  if (!editor) {
    return { ok: false, error: "no editor or file manager available" };
  }

  try {
    const child = spawn(editor.command, [...editor.args, abs], {
      detached: true,
      stdio: "ignore",
      env: process.env,
    });
    child.unref();
    return { ok: true, editor };
  } catch (err) {
    return {
      ok: false,
      error: `failed to open ${editor.label}: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}
