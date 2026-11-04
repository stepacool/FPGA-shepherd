#!/usr/bin/env node
/**
 * Download Surfer WASM (pages_build) into public/surfer/ for same-origin embeds.
 * Skips when surfer_bg.wasm is already present unless FORCE_SURFER=1.
 * Requires Node ≥ 18 (see check-node.mjs / package.json engines).
 */
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const webRoot = join(__dirname, "..");
const outDir = join(webRoot, "public", "surfer");
const marker = join(outDir, "surfer_bg.wasm");
const ARTIFACT =
  "https://gitlab.com/surfer-project/surfer/-/jobs/artifacts/main/download?job=pages_build";

async function main() {
  if (existsSync(marker) && process.env.FORCE_SURFER !== "1") {
    console.log("surfer: public/surfer already present — skip download");
    return;
  }

  mkdirSync(outDir, { recursive: true });
  const zipPath = join(webRoot, ".surfer-pages.zip");
  const extractDir = join(webRoot, ".surfer-extract");

  console.log("surfer: downloading WASM build (~12MB)…");
  if (typeof fetch !== "function") {
    console.error("surfer: need Node ≥ 18 (fetch) — try `nvm use 20`");
    process.exit(1);
  }
  const res = await fetch(ARTIFACT);
  if (!res.ok) {
    console.error(`surfer: download failed HTTP ${res.status}`);
    process.exit(1);
  }
  writeFileSync(zipPath, Buffer.from(await res.arrayBuffer()));

  rmSync(extractDir, { recursive: true, force: true });
  mkdirSync(extractDir, { recursive: true });
  try {
    execFileSync("unzip", ["-q", "-o", zipPath, "-d", extractDir], { stdio: "inherit" });
  } catch {
    execFileSync(
      "python3",
      [
        "-c",
        `import zipfile; zipfile.ZipFile(${JSON.stringify(zipPath)}).extractall(${JSON.stringify(extractDir)})`,
      ],
      { stdio: "inherit" },
    );
  }

  const src = join(extractDir, "pages_build");
  const needed = [
    "surfer.js",
    "surfer_bg.wasm",
    "surfer.d.ts",
    "manifest.json",
    "favicon.ico",
    "integration.js",
    "index.html",
  ];
  for (const name of needed) {
    const from = join(src, name);
    if (!existsSync(from)) {
      console.error(`surfer: missing ${name} in artifact`);
      process.exit(1);
    }
    if (name === "index.html") continue;
    cpSync(from, join(outDir, name));
  }

  let html = readFileSync(join(src, "index.html"), "utf8");
  html = html.replace(/integrity="[^"]*"/g, "");
  html = html.replace(
    "/*SURFER_SETUP_HOOKS*/",
    `try { window.parent.postMessage({ type: "shepherd-surfer-ready" }, "*"); } catch (e) {}`,
  );
  writeFileSync(join(outDir, "index.html"), html);

  rmSync(zipPath, { force: true });
  rmSync(extractDir, { recursive: true, force: true });
  console.log(`surfer: ready at ${outDir}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
