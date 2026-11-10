import "server-only";

import { spawn, type ChildProcess } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

import { getRun, latestSuccessfulBuild, latestSuccessfulUpload } from "./db";
import {
  hasBitstream,
  hasShepherdToml,
  lockPath,
  repoRoot,
  resolveProject,
} from "./paths";

/** Commands the demo UI may start (Shepherd owns the toolchain). */
export const ALLOWED = new Set([
  "init",
  "build",
  "upload",
  "verify",
  "reset",
  "doctor",
  "explain",
  "ask",
  "sim",
  "lint",
  "test",
  "report",
]);

/** Require a successful build (or an on-disk bitstream) before these. */
export const REQUIRES_BUILD = new Set(["upload", "sim", "test", "report"]);

/** Require a successful upload before these. */
export const REQUIRES_UPLOAD = new Set(["verify"]);

export type SpawnRequest = {
  project: string;
  command: string;
  /** Extra argv after the command (e.g. ask question, --fix, testbench). */
  args?: string[];
  runId?: string;
  showBackend?: boolean;
};

export type SpawnResult =
  | { ok: true; runId: string; pid: number }
  | { ok: false; error: string };

/** In-process pid map so Cancel works before the first DB write. */
const localChildren = new Map<string, { pid: number; child: ChildProcess }>();

export function newRunId(): string {
  const now = new Date();
  const stamp = now
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d{3}Z$/, "")
    .replace("T", "T");
  // e.g. 20261103T022156-a1b2 (matches Shepherd's new_run_id shape)
  return `${stamp.slice(0, 15)}-${crypto.randomBytes(2).toString("hex")}`;
}

export function lockStatus(projectPath: string): {
  locked: boolean;
  detail?: string;
} {
  const project = resolveProject(projectPath);
  const file = lockPath(project);
  if (!fs.existsSync(file)) {
    return { locked: false };
  }
  const parts = fs.readFileSync(file, "utf8").trim().split(/\s+/);
  const pid = Number(parts[0]);
  const runId = parts[1] ?? "?";
  if (!Number.isFinite(pid)) {
    return { locked: false };
  }
  try {
    process.kill(pid, 0);
    return { locked: true, detail: `run ${runId}, pid ${pid}` };
  } catch {
    // Stale lock — Shepherd would reclaim; UI treats as free.
    return { locked: false };
  }
}

/**
 * Spawn: `uv run --directory <repo> shepherd <cmd> … --yes -P <project> --run-id <id>`
 *
 * New process group (`detached`), no TTY. See docs/ui-spawn.md.
 */
export function spawnShepherd(req: SpawnRequest): SpawnResult {
  const command = req.command.trim();
  if (!ALLOWED.has(command)) {
    return { ok: false, error: `command not allowed: ${command}` };
  }

  let project: string;
  try {
    project = resolveProject(req.project);
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    };
  }

  // `init` scaffolds shepherd.toml; every other command needs an existing project.
  if (command !== "init" && !hasShepherdToml(project)) {
    return {
      ok: false,
      error:
        "not a Shepherd project (no shepherd.toml) — open a folder that contains one",
    };
  }

  if (REQUIRES_BUILD.has(command)) {
    const built = latestSuccessfulBuild(project) != null || hasBitstream(project);
    if (!built) {
      return {
        ok: false,
        error: `run Build successfully before ${command}`,
      };
    }
  }

  if (REQUIRES_UPLOAD.has(command)) {
    if (latestSuccessfulUpload(project) == null) {
      return {
        ok: false,
        error: `run Upload successfully before ${command}`,
      };
    }
  }

  const lock = lockStatus(project);
  if (lock.locked) {
    return {
      ok: false,
      error: `run already active (${lock.detail ?? "lock held"})`,
    };
  }

  const runId = req.runId?.trim() || newRunId();
  const repo = repoRoot();
  // Globals may sit before or after the subcommand; we pass both styles' essentials
  // after the command (CLI re-declares --yes / -P / --run-id on each command).
  const argv = [
    "run",
    "--directory",
    repo,
    "shepherd",
    command,
    ...(req.args ?? []),
    "--yes",
    "-P",
    project,
    "--run-id",
    runId,
  ];
  if (req.showBackend) {
    argv.push("--show-backend");
  }

  const child = spawn("uv", argv, {
    cwd: project,
    detached: true,
    stdio: "ignore",
    env: process.env,
  });

  if (child.pid == null) {
    return { ok: false, error: "failed to spawn shepherd (no pid)" };
  }

  localChildren.set(runId, { pid: child.pid, child });
  child.unref();

  // Best-effort: record spawn metadata for debugging (Shepherd writes pid itself).
  try {
    const dir = path.join(project, ".shepherd", "runs", runId);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(
      path.join(dir, "ui-spawn.json"),
      JSON.stringify({
        pid: child.pid,
        argv: ["uv", ...argv],
        started_at: new Date().toISOString(),
      }),
    );
  } catch {
    // non-fatal
  }

  return { ok: true, runId, pid: child.pid };
}

export type CancelResult =
  | { ok: true; signal: string; pgid: number }
  | { ok: false; error: string };

/**
 * Cancel: SIGTERM the process group, then SIGKILL after `killAfterMs`.
 */
export function cancelShepherd(
  projectPath: string,
  runId: string,
  killAfterMs = 2000,
): CancelResult {
  const project = resolveProject(projectPath);
  const row = getRun(project, runId);
  const local = localChildren.get(runId);
  const pgid = row?.pgid ?? row?.pid ?? local?.pid;
  if (pgid == null) {
    return { ok: false, error: `no pid/pgid for run ${runId}` };
  }

  try {
    process.kill(-pgid, "SIGTERM");
  } catch (err) {
    // Fallback: kill the single process.
    try {
      process.kill(pgid, "SIGTERM");
    } catch {
      return {
        ok: false,
        error: `cancel failed: ${err instanceof Error ? err.message : String(err)}`,
      };
    }
  }

  setTimeout(() => {
    try {
      process.kill(-pgid, "SIGKILL");
    } catch {
      try {
        process.kill(pgid, "SIGKILL");
      } catch {
        /* already gone */
      }
    }
    localChildren.delete(runId);
  }, killAfterMs).unref();

  return { ok: true, signal: "SIGTERM", pgid };
}
