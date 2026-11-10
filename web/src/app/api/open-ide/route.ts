import { NextResponse } from "next/server";

import { openInEditor } from "@/lib/editors";
import { hasShepherdToml } from "@/lib/paths";

export const runtime = "nodejs";

export async function POST(req: Request) {
  let body: { project?: string; editorId?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid JSON" }, { status: 400 });
  }

  const project = (body.project ?? "").trim();
  if (!project) {
    return NextResponse.json(
      { ok: false, error: "project required" },
      { status: 400 },
    );
  }

  if (!hasShepherdToml(project)) {
    return NextResponse.json(
      {
        ok: false,
        error:
          "not a Shepherd project (no shepherd.toml) — open a project first",
      },
      { status: 400 },
    );
  }

  const result = openInEditor(project, body.editorId);
  if (!result.ok) {
    return NextResponse.json(result, { status: 500 });
  }
  return NextResponse.json({
    ok: true,
    editorId: result.editor.id,
    label: result.editor.label,
  });
}
