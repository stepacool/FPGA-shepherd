import { NextResponse } from "next/server";

import { activeRun, latestRun, latestSuccessfulBuild } from "@/lib/db";
import { hasBitstream, sourcesStamp } from "@/lib/paths";
import { lockStatus } from "@/lib/spawnShepherd";
import { readProjectToml } from "@/lib/toml";

export const runtime = "nodejs";

export async function GET(req: Request) {
  const project = new URL(req.url).searchParams.get("project");
  if (!project) {
    return NextResponse.json({ error: "project query required" }, { status: 400 });
  }
  try {
    const toml = readProjectToml(project);
    const latest = latestRun(project);
    const active = activeRun(project);
    const lock = lockStatus(project);
    const lastBuildOk = latestSuccessfulBuild(project);
    const buildReady = lastBuildOk != null || hasBitstream(project);
    const stamp = sourcesStamp(project, toml.sources);
    return NextResponse.json({
      project,
      board: toml.board,
      top: toml.top,
      sources: toml.sources,
      sourcesStamp: stamp,
      latest,
      active,
      lock,
      buildReady,
      lastBuildOk,
    });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : String(err) },
      { status: 400 },
    );
  }
}
