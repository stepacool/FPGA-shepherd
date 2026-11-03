import { NextResponse } from "next/server";

import { eventsAfter, getRun } from "@/lib/db";

export const runtime = "nodejs";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const project = url.searchParams.get("project");
  const runId = url.searchParams.get("runId");
  const after = Number(url.searchParams.get("after") ?? "0");
  if (!project || !runId) {
    return NextResponse.json(
      { error: "project and runId query required" },
      { status: 400 },
    );
  }
  try {
    const run = getRun(project, runId);
    const events = eventsAfter(project, runId, Number.isFinite(after) ? after : 0);
    return NextResponse.json({ run, events });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : String(err) },
      { status: 400 },
    );
  }
}
