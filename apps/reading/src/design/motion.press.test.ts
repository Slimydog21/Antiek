/**
 * The shared `press` recipe conserves its footprint: at rest the element
 * casts shadow-z1 (3px 3px); hover moves it by (-0.5, -0.5) and casts 3.5px;
 * press moves it by (+0.5, +0.5) and casts 2.5px. Offset plus shadow is 3px
 * in every state, and transform and box-shadow share one transition, so it
 * stays 3px mid-flight too. The pre-fix recipe (transition-transform only,
 * hover -2px + an 8px shadow, press +2px + none) fails every assertion here.
 */
import { describe, expect, it } from "vitest";

import { press } from "./motion";

const REST = 3; // shadow-z1: 3px 3px

function state(prefix: "hover" | "active") {
  const cls = press.split(/\s+/);
  const t = (axis: "x" | "y") => {
    const m = cls.map((c) => c.match(new RegExp(`^${prefix}:(-?)translate-${axis}-\\[([\\d.]+)px\\]$`))).find(Boolean);
    return m ? (m[1] ? -1 : 1) * Number(m[2]) : 0;
  };
  const shadows = cls
    .map((c) => c.match(new RegExp(`^(dark:)?${prefix}:shadow-\\[([\\d.]+)px_([\\d.]+)px_0_0_var\\(--([\\w-]+)\\)\\]$`)))
    .filter((m): m is RegExpMatchArray => !!m)
    .map((m) => ({ dark: !!m[1], x: Number(m[2]), y: Number(m[3]), colour: m[4] }));
  return { tx: t("x"), ty: t("y"), shadows };
}

describe("motion.ts press — conserved footprint", () => {
  it("transitions transform and box-shadow together", () => {
    expect(press).toMatch(/(^|\s)transition-\[transform,box-shadow\](\s|$)/);
    expect(press).not.toMatch(/(^|\s)transition-transform(\s|$)/);
  });

  for (const s of ["hover", "active"] as const) {
    it(`${s}: offset + shadow equals the resting 3px on both axes, day and night`, () => {
      const { tx, ty, shadows } = state(s);
      expect(shadows.map((x) => x.dark).sort()).toEqual([false, true]);
      for (const sh of shadows) {
        expect(tx + sh.x).toBe(REST);
        expect(ty + sh.y).toBe(REST);
        expect(sh.colour).toBe(sh.dark ? "sun-deep" : "fixed-ink");
      }
    });
  }

  it("press is quicker than the lift (duration-fast on :active)", () => {
    expect(press).toMatch(/(^|\s)active:duration-fast(\s|$)/);
    expect(press).toMatch(/(^|\s)duration-base(\s|$)/);
  });
});
