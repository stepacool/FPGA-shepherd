import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { NextResponse } from "next/server";

import { repoRoot } from "@/lib/paths";

export const runtime = "nodejs";

type DirEntry = {
  name: string;
  path: string;
  hasShepherdToml: boolean;
};

function listDirs(dir: string): DirEntry[] {
  const entries: DirEntry[] = [];
  let names: string[];
  try {
    names = fs.readdirSync(dir);
  } catch {
    return [];
  }
  for (const name of names) {
    if (name.startsWith(".") && name !== ".shepherd") continue;
    const full = path.join(dir, name);
    let st: fs.Stats;
    try {
      st = fs.lstatSync(full);
    } catch {
      continue;
    }
    if (!st.isDirectory() || st.isSymbolicLink()) continue;
    entries.push({
      name,
      path: full,
      hasShepherdToml: fs.existsSync(path.join(full, "shepherd.toml")),
    });
  }
  entries.sort((a, b) => a.name.localeCompare(b.name));
  return entries;
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const requested = url.searchParams.get("path");
  const home = os.homedir();
  const repo = repoRoot();

  let current = requested ? path.resolve(requested) : repo;
  if (!fs.existsSync(current) || !fs.statSync(current).isDirectory()) {
    current = home;
  }

  const parent = path.dirname(current);
  return NextResponse.json({
    path: current,
    parent: parent !== current ? parent : null,
    home,
    repo,
    entries: listDirs(current),
  });
}
