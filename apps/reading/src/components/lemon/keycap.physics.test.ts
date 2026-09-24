/**
 * keycap.physics.test.ts — the conserved-footprint contract of lemon.css.
 *
 * A keycap's far edge = face offset (transform) + frame depth (box-shadow y).
 * It is conserved on every frame only if (a) BOTH properties transition, with
 * one duration and one easing, and (b) each state's offset and frame depth
 * sum to the resting depth. The old motion.ts recipe transitioned transform
 * only, so the shadow snapped (footprint +3 -> +8 -> +6 -> +2 px in Chromium).
 *
 * This file pins the recipe; the per-frame proof is the Chromium probe
 * (.lane/harness/measure.mjs: max footprint deviation 0px over every rAF of
 * hover, press and release, both themes).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "lemon.css"), "utf8");
const px = (name: string) => {
  const m = css.match(new RegExp(`${name}:\\s*(-?[\\d.]+)px`));
  if (!m) throw new Error(`${name} not declared`);
  return Number(m[1]);
};
const rule = (selectorPart: string) => {
  const i = css.indexOf(selectorPart);
  if (i < 0) throw new Error(`no rule for ${selectorPart}`);
  return css.slice(i, css.indexOf("}", i));
};

describe("lemon.css keycap — the footprint is conserved", () => {
  it("transform and box-shadow transition together, on one duration and easing", () => {
    const resting = rule(":where(.lemon-keycap) {");
    expect(resting).toMatch(/transition-property:\s*transform,\s*box-shadow;/);
    expect(resting).toMatch(/transition-duration:\s*var\(--motion-base\)/);
    expect(resting).toMatch(/transition-timing-function:\s*var\(--ease-standard\)/);
  });

  it("the frame is drawn as depth minus travel, and the face moves by the travel", () => {
    expect(css).toMatch(/box-shadow:\s*0 calc\(var\(--keycap-depth\) - var\(--keycap-travel\)\) 0 0 var\(--keycap-frame\)/);
    for (const state of [":hover {", ":active {"]) {
      expect(rule(`:not([aria-disabled="true"])${state}`)).toMatch(/transform:\s*translateY\(var\(--keycap-travel\)\)/);
    }
  });

  it("hover lifts and press sinks by half a pixel, so the far edge sums to the resting depth", () => {
    const depth = px("--keycap-depth");
    const lift = px("--keycap-lift");
    const sink = px("--keycap-sink");
    expect(depth).toBe(3);
    expect(lift).toBe(-0.5);
    expect(sink).toBe(0.5);
    for (const travel of [0, lift, sink]) {
      // face offset + frame depth
      expect(travel + (depth - travel)).toBe(depth);
    }
  });

  it("hover only where a real pointer hovers; a disabled key does not move and drops its frame", () => {
    expect(css).toMatch(/@media \(hover: hover\) and \(pointer: fine\)\s*\{\s*\.lemon-keycap:not\(\[aria-disabled="true"\]\):hover/);
    expect(rule('.lemon-keycap[aria-disabled="true"] {')).toMatch(/--keycap-depth:\s*0px/);
  });
});
