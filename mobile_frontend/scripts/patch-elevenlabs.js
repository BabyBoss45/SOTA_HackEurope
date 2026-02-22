/**
 * Build-time patch for @elevenlabs/client
 *
 * Replaces `.error_event.` with `.error_event?.` in dist files to prevent
 * TypeError when the SDK's handleErrorEvent receives an event without
 * an error_event property.
 *
 * Idempotent: `.error_event?.` does not contain the substring `.error_event.`
 * (the regex uses a negative lookahead to skip already-patched occurrences).
 *
 * Runs in the `build` script so it applies on every Vercel build,
 * regardless of node_modules cache state.
 */
const fs = require("fs");
const path = require("path");

const distDir = path.join(
  __dirname,
  "..",
  "node_modules",
  "@elevenlabs",
  "client",
  "dist"
);

const targets = ["lib.cjs", "lib.modern.js", "lib.module.js", "lib.umd.js"];

// Match `.error_event.` but NOT `.error_event?.` (already patched)
const pattern = /\.error_event\.(?!\?)/g;
const replacement = ".error_event?.";

let totalPatched = 0;

for (const file of targets) {
  const filePath = path.join(distDir, file);
  if (!fs.existsSync(filePath)) {
    console.log(`[patch-elevenlabs] SKIP ${file} (not found)`);
    continue;
  }

  const content = fs.readFileSync(filePath, "utf8");
  const count = (content.match(pattern) || []).length;

  if (count === 0) {
    console.log(`[patch-elevenlabs] OK   ${file} (already patched)`);
    continue;
  }

  const patched = content.replace(pattern, replacement);
  fs.writeFileSync(filePath, patched, "utf8");
  console.log(`[patch-elevenlabs] PATCHED ${file} — ${count} occurrence(s)`);
  totalPatched += count;
}

console.log(
  `[patch-elevenlabs] Done. ${totalPatched} total occurrence(s) patched.`
);
