/**
 * entryChunk.test.ts — I14: the two entry-safe contract modules carry only
 * `import type` toward the lazy chunk, and no entry-chunk file statically
 * imports a lazy contract module.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// vitest runs from apps/reading (the gate line cds there); `__dirname` is
// preferred when the runner provides it.
const here = typeof __dirname === "string" ? __dirname : resolve(process.cwd(), "src/workspace/contracts");
const read = (rel: string) => readFileSync(resolve(here, rel), "utf8");

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
  // SPR-07: workspace/agent/* is lazy too (reached through CompanionPane
  // or by import() from shortcuts.ts); a static `./agent/` import is a leak.
  const LAZY = /contracts\/(index|selection|treeStore|openers|adapters)|agent\//;
  for (const f of ENTRY) {
    it(f, () => {
      const hits = imports(read(f)).filter((i) => LAZY.test(i.spec));
      expect(hits.map((i) => i.line)).toEqual([]);
    });
  }
});

describe("the lazy-specifier regex (SPR-07 negative control)", () => {
  it("catches a static ./agent/ import", () => {
    const LAZY = /contracts\/(index|selection|treeStore|openers|adapters)|agent\//;
    const hits = imports('import { openAgentPaneFromKey } from "./agent/openAgentPane";\nimport { x } from "./tabTreeHandle";').filter((i) => LAZY.test(i.spec));
    expect(hits.map((i) => i.spec)).toEqual(["./agent/openAgentPane"]);
  });
});
