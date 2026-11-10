import fs from "node:fs";
import path from "node:path";

import { NextResponse } from "next/server";

import { hasShepherdToml } from "@/lib/paths";
import { newRunId, spawnShepherd } from "@/lib/spawnShepherd";

export const runtime = "nodejs";

const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

function sanitizeName(raw: string): string | null {
  const name = raw.trim();
  if (!NAME_RE.test(name)) return null;
  if (name === "." || name === "..") return null;
  return name;
}

export async function POST(req: Request) {
  let body: { parent?: string; name?: string; showBackend?: boolean };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid JSON" }, { status: 400 });
  }

  const name = sanitizeName(body.name ?? "");
  if (!name) {
    return NextResponse.json(
      {
        ok: false,
        error:
          "invalid project name — no spaces; use letters, digits, ., _, - (max 64, must start with alphanumeric)",
      },
      { status: 400 },
    );
  }

  const parentRaw = (body.parent ?? "").trim();
  if (!parentRaw) {
    return NextResponse.json(
      { ok: false, error: "parent folder required" },
      { status: 400 },
    );
  }

  const parent = path.resolve(parentRaw);
  if (!fs.existsSync(parent) || !fs.statSync(parent).isDirectory()) {
    return NextResponse.json(
      { ok: false, error: `parent folder not found: ${parent}` },
      { status: 400 },
    );
  }

  const project = path.join(parent, name);
  if (fs.existsSync(project)) {
    if (!fs.statSync(project).isDirectory()) {
      return NextResponse.json(
        { ok: false, error: `path exists and is not a folder: ${project}` },
        { status: 409 },
      );
    }
    if (hasShepherdToml(project)) {
      return NextResponse.json(
        {
          ok: false,
          error: `already a Shepherd project: ${project}`,
        },
        { status: 409 },
      );
    }
  } else {
    try {
      fs.mkdirSync(project, { recursive: true });
    } catch (err) {
      return NextResponse.json(
        {
          ok: false,
          error: `could not create folder: ${err instanceof Error ? err.message : String(err)}`,
        },
        { status: 500 },
      );
    }
  }

  const runId = newRunId();
  const result = spawnShepherd({
    project,
    command: "init",
    runId,
    showBackend: Boolean(body.showBackend),
  });

  if (!result.ok) {
    return NextResponse.json(result, { status: 409 });
  }

  return NextResponse.json({
    ok: true,
    project,
    runId: result.runId,
    pid: result.pid,
  });
}
