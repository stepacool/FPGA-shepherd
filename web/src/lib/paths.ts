import "server-only";

import fs from "node:fs";
import path from "node:path";

/** Absolute path to the FPGA-shepherd git checkout (parent of `web/`). */
export function repoRoot(): string {
  return path.resolve(process.cwd(), "..");
}

export function resolveProject(projectPath: string): string {
  const abs = path.resolve(projectPath);
  if (!fs.existsSync(abs) || !fs.statSync(abs).isDirectory()) {
    throw new Error(`project folder not found: ${abs}`);
  }
  return abs;
}

export function dbPath(projectPath: string): string {
  return path.join(resolveProject(projectPath), ".shepherd", "shepherd.db");
}

export function lockPath(projectPath: string): string {
  return path.join(resolveProject(projectPath), ".shepherd", "lock");
}

export function shepherdTomlPath(projectPath: string): string {
  return path.join(resolveProject(projectPath), "shepherd.toml");
}

/** True if a packed bitstream exists from a prior successful build. */
export function hasBitstream(projectPath: string): boolean {
  const fsPath = path.join(
    resolveProject(projectPath),
    ".shepherd",
    "build",
    "_build",
    "default",
    "hardware.fs",
  );
  return fs.existsSync(fsPath);
}
