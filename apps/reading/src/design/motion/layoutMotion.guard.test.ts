/**
 * layoutMotion.guard.test.ts — no transition may animate a layout property.
 *
 * motion.ts states the rule ("GPU-cheap only: transform + box-shadow +
 * opacity. No width/height/top animation"), and the 2026-09-23 design audit
 * (M5) found it broken in seven places: the side docks animated `width` (the
 * reading column reflowed every frame), the mascot strolled on `left`/`top`
 * (one layout per frame for 900ms), three meters animated `width`, and three
 * `transition-all`s would animate any future layout change. A transition on
 * a layout property costs a layout per frame; transform and opacity do not.
 *
 * What counts, in src/ (tests, stories and snapshots excluded):
 *   - the Tailwind class `transition-all`;
 *   - a Tailwind arbitrary `transition-[...]` naming a layout property;
 *   - a CSS or inline transition (`transition:`, `transition-property:`,
 *     `style.transition =`, a React style `transition:` string) whose value
 *     names a layout property or `all`.
 * Limits, stated: framer-motion `animate={{ width }}` / `layout` and CSS
 * keyframes that move layout properties are not scanned here.
 *
 * A grandfathered file may only shrink. To fix a site: snap the layout and
 * fade the content (opacity), move with `transform`, scale a meter with
 * `scaleX`, or name the properties you mean instead of `all`.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..", ".."); // apps/reading/src
const APP = join(SRC, "..");

/** Grandfathered sites, per file. Shrink only. */
const BASELINE: Record<string, number> = {
  // The Settings quota bar (transition-all on a width fill) belongs to the
  // design wave that owns Settings on 2026-09-23; that lane removes it.
  "src/modes/Settings/index.tsx": 1,
};

const LAYOUT =
  "(?:width|height|min-width|max-width|min-height|max-height|left|top|right|bottom|inset|margin[\\w-]*|padding[\\w-]*|all)";
const RULES: { name: string; re: RegExp }[] = [
  { name: "transition-all", re: /(?<![\w-])transition-all(?![\w-])/g },
  {
    name: "transition-[layout]",
    re: new RegExp(`transition-\\[[^\\]]*(?<![\\w-])${LAYOUT}(?![\\w-])[^\\]]*\\]`, "g"),
  },
  {
    name: "transition: layout",
    re: new RegExp(
      `transition(?:-property)?["']?\\s*[:=]\\s*["'\`]?[^;"'\`\\n]*(?<![\\w-])${LAYOUT}(?![\\w-])`,
      "g",
    ),
  },
];

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "__snapshots__" || name === "__matrix__") continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(tsx?|css)$/.test(name) && !/\.(test|stories)\.tsx?$/.test(name)) out.push(p);
  }
  return out;
}

function findings(): Map<string, string[]> {
  const byFile = new Map<string, string[]>();
  for (const file of walk(SRC)) {
    const rel = relative(APP, file);
    readFileSync(file, "utf8")
      .split("\n")
      .forEach((line, i) => {
        for (const { name, re } of RULES) {
          re.lastIndex = 0;
          if (re.test(line)) {
            const list = byFile.get(rel) ?? [];
            list.push(`${rel}:${i + 1} [${name}] ${line.trim().slice(0, 120)}`);
            byFile.set(rel, list);
            break;
          }
        }
      });
  }
  return byFile;
}

describe("layout-property motion guard", () => {
  it("detects every kind it claims to (negative controls)", () => {
    const hit = (s: string) => RULES.some(({ re }) => ((re.lastIndex = 0), re.test(s)));
    expect(hit('className="h-full transition-all"')).toBe(true);
    expect(hit("transition-[width] duration-150")).toBe(true);
    expect(hit("transition-[opacity,max-height]")).toBe(true);
    expect(hit("el.style.transition = `left ${ms}ms ease-in-out, top ${ms}ms`;")).toBe(true);
    expect(hit("  transition: width 200ms ease;")).toBe(true);
    expect(hit('style={{ transition: "height 1s" }}')).toBe(true);
    // Compositor-only motion and colour transitions pass.
    expect(hit("transition-transform duration-base ease-standard")).toBe(false);
    expect(hit("transition-[transform,box-shadow]")).toBe(false);
    expect(hit("transition-[opacity,transform] duration-base")).toBe(false);
    expect(hit("el.style.transition = `transform ${ms}ms ease-in-out`;")).toBe(false);
    expect(hit("  transition: opacity 150ms var(--ease-standard);")).toBe(false);
    expect(hit("transition-colors hover:bg-ice-2")).toBe(false);
  });

  it("no file animates a layout property beyond its grandfathered count", () => {
    const over: string[] = [];
    for (const [file, sites] of findings()) {
      if (sites.length > (BASELINE[file] ?? 0)) over.push(...sites);
    }
    expect(over, `layout-property transitions:\n${over.join("\n")}`).toEqual([]);
  });
});
