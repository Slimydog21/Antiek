/**
 * switcherChunk.test.ts — SPR-04 M4/M5 module-boundary census (fs + regex).
 * The pure layers import values only from the entry-safe `../contracts/tree`;
 * the host statically names no contract and no lazy switcher module; the
 * one store-naming file never calls the census-guarded project writer and
 * never constructs the adapter-only node source; one GEAR_TOGGLE listener.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const here = typeof __dirname === "string" ? __dirname : resolve(process.cwd(), "src/workspace/switcher");
const read = (f: string) => readFileSync(join(here, f), "utf8");

function imports(src: string): { spec: string; typeOnly: boolean; line: string }[] {
  const out: { spec: string; typeOnly: boolean; line: string }[] = [];
  const re = /^\s*import\s+(type\s+)?[\s\S]*?from\s+["']([^"']+)["'];?\s*$/gm;
  for (const m of src.matchAll(re)) out.push({ spec: m[2], typeOnly: Boolean(m[1]), line: m[0].trim() });
  for (const m of src.matchAll(/^\s*import\s+["']([^"']+)["'];?\s*$/gm)) out.push({ spec: m[1], typeOnly: false, line: m[0].trim() });
  return out;
}

describe("the pure layers", () => {
  for (const f of ["switcherModel.ts", "switcherKeys.ts"]) {
    it(`${f} value-imports only ../contracts/tree (or sibling switcher modules) and type-imports ../contracts/selection`, () => {
      const all = imports(read(f));
      for (const i of all) {
        if (i.spec === "../contracts/selection") expect(i.typeOnly, i.line).toBe(true);
        if (i.typeOnly) continue;
        expect(["../contracts/tree"].includes(i.spec) || i.spec.startsWith("./"), i.line).toBe(true);
        expect(i.spec, i.line).not.toMatch(/companionStore|tabTreeStore|contracts\/(index|selection|treeStore|openers|adapters)|zustand|react/);
      }
    });
  }
});

describe("the entry-safe host", () => {
  it("GearSwitchHost never statically imports contracts/, switcherModel, GearSwitch or gearActions", () => {
    const all = imports(read("GearSwitchHost.tsx"));
    for (const i of all) expect(i.spec, i.line).not.toMatch(/contracts\/|switcherModel|switcherKeys|\.\/GearSwitch$|gearActions/);
    expect(read("GearSwitchHost.tsx")).toMatch(/lazy\(\(\) => import\("\.\/GearSwitch"\)\)/);
  });
});

describe("the one store-naming file", () => {
  it("gearActions.ts contains neither .selectProject( nor the adapter-only node-source literal", () => {
    const src = read("gearActions.ts");
    expect(src).not.toMatch(/\.selectProject\(/);
    expect(src).not.toMatch(/\bkind:\s*"investigation"/);
    expect(src).toContain("ffx-kpa-spr-04 M4");
  });
  it("no other switcher module names a store", () => {
    for (const f of ["switcherModel.ts", "switcherKeys.ts", "GearSwitchHost.tsx"]) {
      expect(read(f), f).not.toMatch(/useSelection|useCompanion|useTabTrees|useWorkspace|spawnNewTab/);
    }
    // The surface reads stores (hooks) but writes only through gearActions.
    const surface = read("GearSwitch.tsx");
    expect(surface).not.toMatch(/\.getState\(\)\.(selectProject|selectSubProject|selectAgent|openAgentTab|activateAgentTab|spawnTab)/);
    expect(surface).not.toMatch(/spawnNewTab|toggleProjectPicker/);
  });
});

describe("one toggle listener", () => {
  it("exactly one addEventListener(SHORTCUT_EVENTS.GEAR_TOGGLE in the switcher dir, in GearSwitchHost", () => {
    const files = readdirSync(here).filter((n) => /\.tsx?$/.test(n) && !/\.test\.|\.stories\./.test(n));
    const hits = files.flatMap((n) => {
      const count = read(n).split("addEventListener(SHORTCUT_EVENTS.GEAR_TOGGLE").length - 1;
      return count ? [{ file: n, count }] : [];
    });
    expect(hits).toEqual([{ file: "GearSwitchHost.tsx", count: 1 }]);
  });
  it("the topbar content renders <PreBackendTreeFeed /> exactly once in source", () => {
    expect(read("GearSwitch.tsx").split("<PreBackendTreeFeed />").length - 1).toBe(1);
  });
});
