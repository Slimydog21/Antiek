/**
 * WernerRig.test.tsx — the vector walk-cycle rig (SPR-06 M1).
 *
 * What this proves at the UNIT level (the deterministic half):
 *  - the rig renders the canonical Werner mark (one penguin, not a fork);
 *  - it renders the vector LIMBS — two feet + two flippers — each carrying the
 *    rig class the walk signal drives;
 *  - the limb classes are DESCENDANT-driven (they animate only when an ancestor
 *    carries `werner-waddle` / `werner-step`), so the rig owns NO motion source
 *    of its own — there is no inline animation / no timer in the component;
 *  - the limbs are decorative (aria-hidden) so the labelled Werner mark stays
 *    the single accessible name.
 *
 * What this DELIBERATELY does NOT prove here (rigor #1 — honest about the
 * limit): "the feet actually MOVE across two mid-stroll frames" is a real
 * BROWSER pixel-diff, not a jsdom assertion — jsdom runs no animation. That
 * proof is the M1 sub-test in e2e/_ams/penguin.spec.ts (the feet-region
 * pixel-diff). This file pins the structural contract that makes that motion
 * possible; the e2e gate is the durable proof the feet are not frozen.
 */
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import WernerRig from "./WernerRig";
import { ROD_BUTT_LOCAL, ROD_TIP_LOCAL } from "./fishingLineGeometry";

/**
 * usePrefersReducedMotion reads window.matchMedia, which jsdom lacks. Stub it as
 * the hotkey/ad/penguin suites do. `setReducedMotion(b)` lets the SPR-04 rest-
 * pose test flip the preference; default is motion-allowed (false).
 */
let reducedMotion = false;
function setReducedMotion(v: boolean): void {
  reducedMotion = v;
}
beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: query.includes("reduce") ? reducedMotion : false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});
afterEach(() => {
  cleanup();
  setReducedMotion(false);
});

describe("WernerRig (SPR-06 M1)", () => {
  it("renders the canonical Werner mark plus the four vector limbs", () => {
    const { container } = render(<WernerRig size={64} label="Project" />);
    // The Werner art (transparent variant) — a labelled role=img with an <img>.
    expect(container.querySelector("img")).not.toBeNull();
    // The four walk-cycle limbs, each carrying its rig class.
    expect(container.querySelector(".werner-rig-foot-l")).not.toBeNull();
    expect(container.querySelector(".werner-rig-foot-r")).not.toBeNull();
    expect(container.querySelector(".werner-rig-flipper-l")).not.toBeNull();
    expect(container.querySelector(".werner-rig-flipper-r")).not.toBeNull();
  });

  it("owns NO motion source — the limbs carry no inline animation (driven by the ancestor walk class)", () => {
    const { container } = render(<WernerRig size={64} />);
    // The rig must NOT set its own `animation` inline: motion comes ONLY from
    // the descendant selectors in waddle.css keyed off the roam's walk class.
    // A regression that inlined an animation (a second motion source) reddens.
    for (const sel of [
      ".werner-rig-foot-l",
      ".werner-rig-foot-r",
      ".werner-rig-flipper-l",
      ".werner-rig-flipper-r",
    ]) {
      const el = container.querySelector(sel) as HTMLElement | null;
      expect(el, `missing limb ${sel}`).not.toBeNull();
      // No inline animation property (style.animation stays empty).
      expect(el!.style.animation, `${sel} must not own an inline animation`).toBe(
        "",
      );
    }
  });

  it("the limbs are decorative (aria-hidden) — the Werner mark is the accessible name", () => {
    const { container } = render(<WernerRig size={64} label="Project" />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg!.getAttribute("aria-hidden")).toBe("true");
    // The single accessible label lives on the Werner mark.
    expect(container.querySelector('[aria-label="Project"]')).not.toBeNull();
  });

  it("renders at the requested size (scales with the mascot footprint)", () => {
    const { container } = render(<WernerRig size={64} />);
    const svg = container.querySelector("svg") as SVGSVGElement | null;
    expect(svg).not.toBeNull();
    expect(svg!.getAttribute("width")).toBe("64");
    expect(svg!.getAttribute("height")).toBe("64");
  });
});

/**
 * SPR-04 — the real rod, gripped in the right flipper.
 *
 * The DETERMINISTIC half: the rod <g> exists, pivots from the grip, the grip
 * overlaps the rod butt (no gap hand↔rod), the rod is token-coloured (no hex),
 * and reduced motion holds a straight neutral rest pose. What this does NOT
 * prove (rigor #1): "the rendered rod is LONGER on screen" + "the line's first
 * point lands on the tip in real pixels" — those are the e2e RULE-2 gate
 * (e2e/_werner/rod-in-hand.spec.ts), since jsdom lays nothing out. This pins the
 * structural contract; the browser gate is the durable proof of length + join.
 */
describe("WernerRig — the rod in the flipper (SPR-04)", () => {
  it("renders the rod as a structured <g> that pivots from the GRIP (transform-origin at the butt)", () => {
    const { container } = render(<WernerRig size={64} />);
    const rod = container.querySelector("[data-werner-rod]") as SVGGElement | null;
    expect(rod, "the rod <g> is missing").not.toBeNull();
    // Pivot at the grip = ROD_BUTT (45,34) — so a future cast swings it from the
    // hand, not the body centre. (Standalone: a structured <g> with a grip
    // transform-origin, not a typed RigPart — SPR-01 is deferred.)
    expect(rod!.style.transformOrigin).toBe(
      `${ROD_BUTT_LOCAL.x}px ${ROD_BUTT_LOCAL.y}px`,
    );
  });

  it("the right flipper GRIPS the rod butt — grip geometry overlaps the butt (no gap)", () => {
    const { container } = render(<WernerRig size={64} />);
    const flipperR = container.querySelector(
      ".werner-rig-flipper-r",
    ) as SVGGElement | null;
    expect(flipperR, "the right flipper is missing").not.toBeNull();
    // The flipper carries a curl ellipse seated ON the rod butt (45,34): same
    // pivot, and an ellipse centred at the grip point that overlaps the rod's
    // butt cap → the hand reads as closed around the shaft, no gap.
    expect(flipperR!.style.transformOrigin).toBe(
      `${ROD_BUTT_LOCAL.x}px ${ROD_BUTT_LOCAL.y}px`,
    );
    const grip = flipperR!.querySelector("ellipse");
    expect(grip, "the flipper has no grip ellipse").not.toBeNull();
    const gx = Number(grip!.getAttribute("cx"));
    const gy = Number(grip!.getAttribute("cy"));
    const grx = Number(grip!.getAttribute("rx"));
    const gry = Number(grip!.getAttribute("ry"));
    // The grip ellipse must actually contain / touch the rod butt point — i.e.
    // the rod's butt sits inside the closed hand (overlap, not adjacency).
    const dx = (gx - ROD_BUTT_LOCAL.x) / grx;
    const dy = (gy - ROD_BUTT_LOCAL.y) / gry;
    expect(
      dx * dx + dy * dy,
      "the flipper grip does not overlap the rod butt (a gap between hand and rod)",
    ).toBeLessThanOrEqual(1);
  });

  it("the rod is token-coloured — no raw hex on the rod paint", () => {
    const { container } = render(<WernerRig size={64} />);
    const rod = container.querySelector("[data-werner-rod]") as SVGGElement | null;
    expect(rod).not.toBeNull();
    const painted = rod!.querySelectorAll("[stroke], [fill]");
    expect(painted.length).toBeGreaterThan(0);
    painted.forEach((el) => {
      const stroke = el.getAttribute("stroke");
      const fill = el.getAttribute("fill");
      for (const paint of [stroke, fill]) {
        if (paint && paint !== "none") {
          expect(paint, `raw colour on the rod: ${paint}`).toMatch(/var\(--werner-/);
          expect(paint).not.toMatch(/#[0-9a-fA-F]{3,8}/);
        }
      }
    });
  });

  it("the shaft TAPERS — the butt segment is wider than the tip segment", () => {
    const { container } = render(<WernerRig size={64} />);
    const rod = container.querySelector("[data-werner-rod]") as SVGGElement | null;
    const widths = Array.from(rod!.querySelectorAll("path[stroke-width]")).map(
      (p) => Number(p.getAttribute("stroke-width")),
    );
    expect(widths.length, "the rod has no shaft segments").toBeGreaterThan(1);
    // The first (butt) segment must be strictly wider than the last (tip).
    expect(widths[0]).toBeGreaterThan(widths[widths.length - 1]);
  });

  it("rests STRAIGHT under reduced motion — the bend collapses (no mid-cast flex)", () => {
    setReducedMotion(true);
    const { container } = render(<WernerRig size={64} bend={6} />);
    const rod = container.querySelector("[data-werner-rod]") as SVGGElement | null;
    const segs = Array.from(rod!.querySelectorAll("path[d]")).map((p) =>
      p.getAttribute("d"),
    );
    expect(segs.length).toBeGreaterThan(1);
    // A straight rod: every segment endpoint lies on the butt→tip chord (within
    // a hair of float noise). Bend would bow them off the chord.
    const ax = ROD_TIP_LOCAL.x - ROD_BUTT_LOCAL.x;
    const ay = ROD_TIP_LOCAL.y - ROD_BUTT_LOCAL.y;
    const len = Math.hypot(ax, ay);
    for (const d of segs) {
      const pts = d!.match(/-?\d+(\.\d+)?/g)!.map(Number);
      for (let i = 0; i < pts.length; i += 2) {
        const x = pts[i];
        const y = pts[i + 1];
        // Perpendicular distance from the point to the butt→tip line.
        const perp =
          Math.abs((x - ROD_BUTT_LOCAL.x) * ay - (y - ROD_BUTT_LOCAL.y) * ax) /
          len;
        expect(
          perp,
          `reduced-motion rod is not straight (point ${x},${y} bows ${perp.toFixed(2)} off the chord)`,
        ).toBeLessThan(0.01);
      }
    }
  });

  it("FLEXES when bend is applied with motion allowed (the rest-pose guard is conditional, not always-on)", () => {
    // Counterpart to the reduced-motion test: prove bend actually bows the shaft
    // when motion IS allowed — otherwise the straight-rest test could pass
    // vacuously (a rod that never bends).
    const { container } = render(<WernerRig size={64} bend={6} />);
    const rod = container.querySelector("[data-werner-rod]") as SVGGElement | null;
    const segs = Array.from(rod!.querySelectorAll("path[d]")).map((p) =>
      p.getAttribute("d"),
    );
    const ax = ROD_TIP_LOCAL.x - ROD_BUTT_LOCAL.x;
    const ay = ROD_TIP_LOCAL.y - ROD_BUTT_LOCAL.y;
    const len = Math.hypot(ax, ay);
    let maxPerp = 0;
    for (const d of segs) {
      const pts = d!.match(/-?\d+(\.\d+)?/g)!.map(Number);
      for (let i = 0; i < pts.length; i += 2) {
        const perp =
          Math.abs(
            (pts[i] - ROD_BUTT_LOCAL.x) * ay - (pts[i + 1] - ROD_BUTT_LOCAL.y) * ax,
          ) / len;
        if (perp > maxPerp) maxPerp = perp;
      }
    }
    expect(maxPerp, "bend did not bow the shaft off the chord").toBeGreaterThan(1);
  });
});

describe("WernerRig — idle fishing marks hidden at rest (SPR-05)", () => {
  it("hides the idle line + fish by default; only the .werner-fishing loop reveals them", () => {
    const { container } = render(<WernerRig size={64} />);
    const line = container.querySelector(".werner-rig-line");
    const fish = container.querySelector(".werner-rig-fish");
    expect(line, "idle line node should exist").not.toBeNull();
    expect(fish, "fish node should exist").not.toBeNull();
    // No .werner-fishing ancestor here — the loop is OFF, which is the production
    // default (ice flag off, reduced motion, or any rest moment). Both marks MUST
    // be opacity 0 by default, else a teal fish + line dangle off a resting
    // Werner (the MAJOR the critic caught: previously only the keyframes hid
    // them, so at rest they showed permanently). The .werner-fishing keyframes
    // animate opacity up only while the gag runs.
    expect(line!.getAttribute("opacity")).toBe("0");
    expect(fish!.getAttribute("opacity")).toBe("0");
  });
});
