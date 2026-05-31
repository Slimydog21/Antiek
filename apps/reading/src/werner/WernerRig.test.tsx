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
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import WernerRig from "./WernerRig";

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
