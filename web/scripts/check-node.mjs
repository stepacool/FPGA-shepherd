#!/usr/bin/env node
/** Fail fast if Node is too old for Next.js 15 / this package. */
const [major, minor] = process.versions.node.split(".").map(Number);
const ok = major > 18 || (major === 18 && minor >= 18);
if (!ok) {
  console.error(
    `web/: need Node ≥ 18.18 (you have v${process.versions.node}).\n` +
      `  Fix:  source ~/.nvm/nvm.sh && nvm use 20\n` +
      `  Then: npm run build`,
  );
  process.exit(1);
}
