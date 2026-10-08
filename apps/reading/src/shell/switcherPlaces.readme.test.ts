/**
 * README-switcher.md must name every export of switcherPlaces.ts (SPR-02 M6
 * gate: "README's exported-API table matches switcherPlaces.ts exports").
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const here = import.meta.dirname ?? __dirname;

describe("README-switcher.md documents every export", () => {
  it("names each exported function and const", () => {
    const src = readFileSync(join(here, "switcherPlaces.ts"), "utf8");
    const readme = readFileSync(join(here, "README-switcher.md"), "utf8");
    const names = [...src.matchAll(/^export (?:function|const) ([A-Za-z_]+)/gm)].map((m) => m[1]);
    expect(names.length).toBeGreaterThan(8);
    const missing = names.filter((n) => !readme.includes(n));
    expect(missing).toEqual([]);
  });
});
