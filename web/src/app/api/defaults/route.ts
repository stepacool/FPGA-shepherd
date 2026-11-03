import path from "node:path";

import { NextResponse } from "next/server";

import { repoRoot } from "@/lib/paths";

export const runtime = "nodejs";

/** Demo helpers: absolute paths under this checkout. */
export async function GET() {
  const root = repoRoot();
  return NextResponse.json({
    repo: root,
    blinky: path.join(root, "examples", "blinky_sv"),
    uart: path.join(root, "examples", "uart_amaranth"),
  });
}
