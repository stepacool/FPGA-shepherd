import { NextResponse } from "next/server";

import { cancelShepherd } from "@/lib/spawnShepherd";

export const runtime = "nodejs";

export async function POST(req: Request) {
  let body: { project?: string; runId?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  if (!body.project || !body.runId) {
    return NextResponse.json(
      { error: "project and runId required" },
      { status: 400 },
    );
  }
  const result = cancelShepherd(body.project, body.runId);
  return NextResponse.json(result, { status: result.ok ? 200 : 400 });
}
