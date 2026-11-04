import fs from "node:fs";
import path from "node:path";

import { NextResponse } from "next/server";

import { resolveProject } from "@/lib/paths";

export const runtime = "nodejs";

const WAVE_EXT = new Set([".vcd", ".fst", ".ghw"]);

/** Serve a project file by absolute path (path-only artifacts; never store blobs in SQLite). */
export async function GET(req: Request) {
  const url = new URL(req.url);
  const project = url.searchParams.get("project");
  const file = url.searchParams.get("path");
  if (!project || !file) {
    return NextResponse.json(
      { error: "project and path query required" },
      { status: 400 },
    );
  }

  let root: string;
  try {
    root = resolveProject(project);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : String(err) },
      { status: 400 },
    );
  }

  const abs = path.resolve(file);
  const rootReal = fs.realpathSync(root);
  let fileReal: string;
  try {
    fileReal = fs.realpathSync(abs);
  } catch {
    return NextResponse.json({ error: "file not found" }, { status: 404 });
  }
  const prefix = rootReal.endsWith(path.sep) ? rootReal : rootReal + path.sep;
  if (fileReal !== rootReal && !fileReal.startsWith(prefix)) {
    return NextResponse.json(
      { error: "path must be inside the project folder" },
      { status: 403 },
    );
  }

  const ext = path.extname(fileReal).toLowerCase();
  if (!WAVE_EXT.has(ext) && ext !== ".log" && ext !== ".fs" && ext !== ".v" && ext !== ".sv") {
    return NextResponse.json({ error: `refusing to serve ${ext || "unknown"}` }, { status: 403 });
  }

  const body = fs.readFileSync(fileReal);
  const type =
    ext === ".vcd"
      ? "text/plain; charset=utf-8"
      : ext === ".log" || ext === ".v" || ext === ".sv"
        ? "text/plain; charset=utf-8"
        : "application/octet-stream";

  return new NextResponse(body, {
    status: 200,
    headers: {
      "Content-Type": type,
      "Content-Length": String(body.byteLength),
      "Cache-Control": "no-store",
      // Surfer (app.surfer-project.org) fetches this URL from the browser.
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
    },
  });
}

export async function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Access-Control-Allow-Headers": "*",
    },
  });
}
