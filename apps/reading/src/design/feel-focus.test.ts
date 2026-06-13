import { readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { contrastRatio, type Rgb } from "../../e2e/_ams/visible";
import { surface, sun } from "./tokens";

const ALLOWLIST = new Set([
  "feel-focus.css",
  "feel-focus.test.ts",
]);

// The shell surfaces that consume the focus ring + the file each lives in. The
// SPR-03 baseline embarrassment was that `.feel-focusable` had ZERO consumers on
// any scene/shell control. SPR-08 M3 closes that — this list is the durable
// coverage guard: every control-bearing shell component must consume the ring.
const SHELL_FOCUS_CONSUMERS = [
  "../shell/NavRail.tsx",
  "../shell/ProductsLauncher.tsx",
  "../shell/SceneChrome.tsx",
  "../shell/ThreadBreadcrumb.tsx",
  "../shell/ProjectTree.tsx",
] as const;

const hex = (h: string): Rgb => ({
  r: parseInt(h.slice(1, 3), 16),
  g: parseInt(h.slice(3, 5), 16),
  b: parseInt(h.slice(5, 7), 16),
});

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

describe("feel-focus — outline-none guard", () => {
  it("focus:outline-none is paired with focus-visible ring in Feel dirs", () => {
    const violations: string[] = [];
    for (const dir of FEEL_DIRS) {
      for (const file of collectTsFiles(dir)) {
        const src = readFileSync(file, "utf8");
        if (!src.includes("focus:outline-none")) continue;
        if (
          !src.includes("focus-visible:ring") &&
          !src.includes("feel-focusable")
        ) {
          violations.push(file);
        }
      }
    }
    expect(violations).toEqual([]);
  });
});

describe("feel-focus — SPR-08 M3 shell coverage (the 1→3 lift; was zero consumers)", () => {
  it("every control-bearing shell component consumes the feel-focusable ring", () => {
    const missing: string[] = [];
    for (const rel of SHELL_FOCUS_CONSUMERS) {
      const src = readFileSync(resolve(import.meta.dirname, rel), "utf8");
      // A component carries focus coverage if it uses the shared ring OR a
      // deliberate explicit `focus-visible:` (e.g. NavRail's home igloo uses an
      // ink outline because a sun ring on a sun button would be invisible).
      if (!src.includes("feel-focusable") && !src.includes("focus-visible:")) {
        missing.push(rel);
      }
    }
    expect(missing, `shell components with NO focus-visible coverage: ${missing.join(", ")}`).toEqual([]);
  });

  it("no shell control uses a BARE :focus border/ring (the rubric level-1 symptom)", () => {
    // `focus:border-…` / `focus:ring-…` / `focus:outline-…` (NOT focus-visible)
    // fires on a MOUSE click — the named failure. ProductsLauncher's search input
    // was the last one; it is now focus-visible.
    const offenders: string[] = [];
    for (const rel of SHELL_FOCUS_CONSUMERS) {
      const src = readFileSync(resolve(import.meta.dirname, rel), "utf8");
      // match `focus:` not preceded by `-visible`/`group-` — i.e. a bare focus:
      const bare = src.match(/(?<!-)(?<!group-)\bfocus:(?:border|ring|outline)/g);
      if (bare && bare.length) offenders.push(`${rel} (${bare.length})`);
    }
    expect(offenders, `bare :focus controls remain: ${offenders.join(", ")}`).toEqual([]);
  });
});

describe("feel-focus — dual-tone ring legibility over the 4 worst scene/chrome cells", () => {
  // The ring is dual-tone: --sun core + --ink halo (feel-focus.css). On each
  // worst surface, the BETTER of {sun, ink} must clear the WCAG 1.4.11 non-text
  // floor of 3:1 — that is what makes the ring legible everywhere without dimming
  // the scene. We use the SAME contrast math as the browser gate (visible.ts).
  // Values READ FROM tokens.ts (no raw hex — token-lint discipline, same as
  // tokens.contrast.test.ts). SUN = brand lemon ring core; HALO = fixed dark ink
  // (== --feel-focus-halo, day --ink) — does NOT invert, so it always contrasts
  // the sun core AND shows on light surfaces. Light/dark chrome cells = the
  // opaque surfaces shell controls sit on.
  const SUN = hex(sun.base); // brand lemon ring core
  const HALO = hex(surface.day[9]); // ink (fixed dark halo == --feel-focus-halo)

  // The four worst cells: the darkest + brightest the scene can paint, plus the
  // two opaque chrome surfaces shell controls sit on (light card, dark card).
  // Coords-free: these are the colour extremes, which is what contrast depends on
  // (the SPR-05 legibility audit's worst-case principle).
  const CELLS: Array<{ name: string; bg: Rgb }> = [
    { name: "black scene (night sky deepest)", bg: { r: 0, g: 0, b: 0 } },
    { name: "white scene (bright Krea art)", bg: { r: 255, g: 255, b: 255 } },
    { name: `light chrome ${surface.day[1]}`, bg: hex(surface.day[1]) },
    { name: `dark chrome ${surface.night[4]}`, bg: hex(surface.night[4]) },
  ];

  const FLOOR = 3.0;

  for (const cell of CELLS) {
    it(`ring is legible over ${cell.name} (best-of {sun,halo} ≥ 3:1)`, () => {
      const sunC = contrastRatio(SUN, cell.bg);
      const haloC = contrastRatio(HALO, cell.bg);
      const best = Math.max(sunC, haloC);
      expect(
        best,
        `over ${cell.name}: sun=${sunC.toFixed(2)} halo=${haloC.toFixed(2)} — neither ring layer clears ${FLOOR}:1`,
      ).toBeGreaterThanOrEqual(FLOOR);
    });
  }

  it("the two ring layers contrast EACH OTHER (the ring reads as a ring), on both themes", () => {
    // Fixed dark halo vs the fixed light sun core — one number, both themes.
    expect(contrastRatio(SUN, HALO)).toBeGreaterThanOrEqual(3.0);
  });
});