import { NextResponse } from "next/server";

import { spawnShepherd } from "@/lib/spawnShepherd";

export const runtime = "nodejs";

export async function POST(req: Request) {
  let body: {
    project?: string;
    command?: string;
    args?: string[];
    runId?: string;
    showBackend?: boolean;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  if (!body.project || !body.command) {
    return NextResponse.json(
      { error: "project and command required" },
      { status: 400 },
    );
  }
  const result = spawnShepherd({
    project: body.project,
    command: body.command,
    args: body.args,
    runId: body.runId,
    showBackend: body.showBackend,
  });
  return NextResponse.json(result, { status: result.ok ? 200 : 409 });
}
