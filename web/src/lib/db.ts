import "server-only";

import fs from "node:fs";

import Database from "better-sqlite3";

import { dbPath, resolveProject } from "./paths";

export type RunRow = {
  id: string;
  project_path: string;
  command: string;
  board: string | null;
  pid: number | null;
  pgid: number | null;
  started_at: string;
  finished_at: string | null;
  verdict: string | null;
};

export type EventRow = {
  id: number;
  run_id: string;
  ts: string;
  kind: string;
  step: string | null;
  level: string | null;
  message: string | null;
  payload_json: string | null;
};

function open(projectPath: string): Database.Database | null {
  const file = dbPath(projectPath);
  if (!fs.existsSync(file)) {
    return null;
  }
  const db = new Database(file, { readonly: true, fileMustExist: true });
  db.pragma("query_only = ON");
  return db;
}

export function latestRun(projectPath: string): RunRow | null {
  resolveProject(projectPath);
  const db = open(projectPath);
  if (!db) return null;
  try {
    return (
      (db
        .prepare(
          "SELECT * FROM runs ORDER BY started_at DESC, rowid DESC LIMIT 1",
        )
        .get() as RunRow | undefined) ?? null
    );
  } finally {
    db.close();
  }
}

export function getRun(projectPath: string, runId: string): RunRow | null {
  resolveProject(projectPath);
  const db = open(projectPath);
  if (!db) return null;
  try {
    return (
      (db.prepare("SELECT * FROM runs WHERE id = ?").get(runId) as
        | RunRow
        | undefined) ?? null
    );
  } finally {
    db.close();
  }
}

export function eventsAfter(
  projectPath: string,
  runId: string,
  afterId = 0,
): EventRow[] {
  resolveProject(projectPath);
  const db = open(projectPath);
  if (!db) return [];
  try {
    return db
      .prepare(
        "SELECT * FROM events WHERE run_id = ? AND id > ? ORDER BY id ASC",
      )
      .all(runId, afterId) as EventRow[];
  } finally {
    db.close();
  }
}

export function activeRun(projectPath: string): RunRow | null {
  resolveProject(projectPath);
  const db = open(projectPath);
  if (!db) return null;
  try {
    return (
      (db
        .prepare(
          "SELECT * FROM runs WHERE finished_at IS NULL ORDER BY started_at DESC LIMIT 1",
        )
        .get() as RunRow | undefined) ?? null
    );
  } finally {
    db.close();
  }
}

/** Latest finished `build` with verdict pass (for gating upload/sim). */
export function latestSuccessfulBuild(projectPath: string): RunRow | null {
  resolveProject(projectPath);
  const db = open(projectPath);
  if (!db) return null;
  try {
    return (
      (db
        .prepare(
          "SELECT * FROM runs WHERE command = 'build' AND verdict = 'pass' "
            + "ORDER BY started_at DESC, rowid DESC LIMIT 1",
        )
        .get() as RunRow | undefined) ?? null
    );
  } finally {
    db.close();
  }
}
