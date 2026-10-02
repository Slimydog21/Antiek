import { readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const ALLOWLIST = new Set([
  "focus.guard.test.ts",
]);

const FEEL_DIRS = [
  resolve(import.meta.dirname, "../workspace"),
  resolve(import.meta.dirname, "../components/windows"),
  resolve(import.meta.dirname, "../modes/ResearchWorkstation"),
];

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

/**
 * Focus guard (FEEL-S5). The shipped focus ring is the Tailwind idiom —
 * `focus-visible:ring-2 ring-sun` on controls, `outline-sun` on
 * panel/window chrome. Any `focus:outline-none` in the Feel dirs must be
 * paired with a focus-visible ring so keyboard focus never disappears.
 */
describe("focus — outline-none guard", () => {
  it("focus:outline-none is paired with focus-visible ring in Feel dirs", () => {
    const violations: string[] = [];
    for (const dir of FEEL_DIRS) {
      for (const file of collectTsFiles(dir)) {
        const src = readFileSync(file, "utf8");
        if (!src.includes("focus:outline-none")) continue;
        if (!src.includes("focus-visible:ring")) {
          violations.push(file);
        }
      }
    }
    expect(violations).toEqual([]);
  });
});
