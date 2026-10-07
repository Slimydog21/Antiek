/**
 * entryChunk.test.ts — I14: the two entry-safe contract modules carry only
 * `import type` toward the lazy chunk, and no entry-chunk file statically
 * imports a lazy contract module.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = fileURLToPath(new URL(".", import.meta.url));
const read = (rel: string) => readFileSync(new URL(rel, `file://${here}`), "utf8");

/** Every static import statement with its specifier and whether it is type-only. */
function imports(src: string): { spec: string; typeOnly: boolean; line: string }[] {
  const out: { spec: string; typeOnly: boolean; line: string }[] = [];
  const re = /^\s*import\s+(type\s+)?[\s\S]*?from\s+["']([^"']+)["'];?\s*$/gm;
  for (const m of src.matchAll(re)) out.push({ spec: m[2], typeOnly: Boolean(m[1]), line: m[0].trim() });
  const side = /^\s*import\s+["']([^"']+)["'];?\s*$/gm;
  for (const m of src.matchAll(side)) out.push({ spec: m[1], typeOnly: false, line: m[0].trim() });
  return out;
}

const LAZY_VALUE_SPECS = [
  "../tabTreeStore", "../tabTree", "../companionStore", "../CompanionPane", "../companionRegistry",
  "../crossPane", "../../lib/api", "../../lib/api/projects", "zustand",
];

describe("entry-safe contract modules", () => {
  for (const file of ["tree.ts", "anchor.ts"]) {
    it(`${file} imports only types from the lazy chunk`, () => {
      const all = imports(read(file));
      const value = all.filter((i) => !i.typeOnly);
      expect(value.map((i) => i.line)).toEqual([]);
      for (const i of all) {
        if (LAZY_VALUE_SPECS.includes(i.spec)) expect(i.typeOnly, i.line).toBe(true);
      }
    });
  }
});

describe("entry-chunk files never statically import a lazy contract module", () => {
  const ENTRY = ["../shortcuts.ts", "../companionVisibility.ts", "../tabTreeHandle.ts"];
  const LAZY = /contracts\/(index|selection|treeStore|openers|adapters)/;
  for (const f of ENTRY) {
    it(f, () => {
      const hits = imports(read(f)).filter((i) => LAZY.test(i.spec));
      expect(hits.map((i) => i.line)).toEqual([]);
    });
  }
});
