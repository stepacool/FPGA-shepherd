import { NextResponse } from "next/server";

import { listEditors } from "@/lib/editors";

export const runtime = "nodejs";

export async function GET() {
  const { available, defaultId } = listEditors();
  return NextResponse.json({
    available: available.map(({ id, label }) => ({ id, label })),
    defaultId,
  });
}
