import { readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const ALLOWLIST = new Set([
  "focus.guard.test.ts",
]);

// The whole app surface. The guard used to scan three "Feel dirs"
// (workspace, components/windows, modes/ResearchWorkstation) — 3 of ~30
// source directories — so an unpaired focus:outline-none in src/modes/Write
// or anywhere else passed unseen (measured 2026-10-02). There is no
// chrome/content split for focus: keyboard focus must never disappear
// anywhere.
const SCAN_DIRS = [resolve(import.meta.dirname, "..")]; // all of src/

function collectTsFiles(dir: string): string[] {
  const out: string[] = [];
  for (const ent of readdirSync(dir, { withFileTypes: true })) {
    if (ent.name.startsWith(".")) continue;
    const p = join(dir, ent.name);
    if (ent.isDirectory()) out.push(...collectTsFiles(p));
    else if (/\.(tsx?|css)$/.test(ent.name) && !ALLOWLIST.has(ent.name)) {
      out.push(p);
    }
  }
  return out;
}

/** Comment spans — a class name named in a comment is not on the element.
 *  Without stripping, `src/index.css` (which DOCUMENTS the idiom in a
 *  comment) false-positives, and a comment mentioning focus-visible:ring
 *  would false-PAIR a real violation. Mirrors scripts/lint_tokens.ts. */
const BLOCK_COMMENT = /\/\*[\s\S]*?\*\//g;
const LINE_COMMENT = /(?<!:)\/\/[^\n]*/g;

function stripComments(source: string): string {
  return source.replace(BLOCK_COMMENT, "").replace(LINE_COMMENT, "");
}

/**
 * Focus guard (FEEL-S5). The shipped focus ring is the Tailwind idiom —
 * `focus-visible:ring-2 ring-sun` on controls, `outline-sun` on
 * panel/window chrome. Any `focus:outline-none` anywhere in src/ must be
 * paired with a focus ring utility in the same file so keyboard focus
 * never disappears. Both ring idioms pair: `focus-visible:ring` (shows on
 * keyboard focus) and plain `focus:ring` (shows on every focus — the
 * stronger, always-on variant several modes already use).
 *
 * Known residual: pairing is per-FILE, not per-element — a file with one
 * paired and one unpaired control passes. Element-level pairing needs JSX
 * awareness this string scan deliberately does not attempt.
 */
describe("focus — outline-none guard", () => {
  it("focus:outline-none is paired with a focus ring, everywhere in src/", () => {
    const violations: string[] = [];
    for (const dir of SCAN_DIRS) {
      for (const file of collectTsFiles(dir)) {
        const src = stripComments(readFileSync(file, "utf8"));
        if (!src.includes("focus:outline-none")) continue;
        if (!src.includes("focus-visible:ring") && !src.includes("focus:ring")) {
          violations.push(file);
        }
      }
    }
    expect(violations).toEqual([]);
  });
});
