import "server-only";

import fs from "node:fs";

import { shepherdTomlPath } from "./paths";

/** Tiny shepherd.toml reader — only board / top / sources for the Project strip. */
export function readProjectToml(projectPath: string): {
  board: string | null;
  top: string | null;
  sources: string[];
} {
  const file = shepherdTomlPath(projectPath);
  if (!fs.existsSync(file)) {
    return { board: null, top: null, sources: [] };
  }
  const text = fs.readFileSync(file, "utf8");
  const board = text.match(/^\s*board\s*=\s*"([^"]+)"/m)?.[1] ?? null;
  const top = text.match(/^\s*top\s*=\s*"([^"]+)"/m)?.[1] ?? null;
  const sourcesBlock = text.match(/^\s*sources\s*=\s*\[([^\]]*)\]/m)?.[1] ?? "";
  const sources = [...sourcesBlock.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  return { board, top, sources };
}
