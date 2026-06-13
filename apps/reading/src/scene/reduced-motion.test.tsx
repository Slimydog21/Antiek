/**
 * reduced-motion.test.tsx — reduced motion is a DESIGN, not an off-switch
 * (ALC SPR-06 M5), proven at the DOM level. The browser-pixel proof (emulated
 * prefers-reduced-motion, zero animated properties beyond the allowed dissolve)
 * is the e2e gate (scene-living.spec.ts); these vitests pin the contract that
 * EVERY animation SPR-06 adds collapses to the SPR-05 static composition:
 *
 *   • DRIFT/PARALLAX → STOP. The reduced seams are the IDENTITY, so the drifting
 *     Mountainscape renders BYTE-IDENTICAL to the static (no-seam) Mountainscape:
 *     the SPR-05 designed pose IS the reduced state (snapshot equality).
 *   • CROSSFADE → near-instant opacity DISSOLVE (opacity only, never a transform,
 *     never a keyframe).
 *
 * This is the "designed mood-matrix cell match" the spec asks for, in the
 * deterministic markup form the SPR-05 matrix harness uses (the live scene story
 * is filterShot-excluded for nondeterminism — so DOM equality is the gate).
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { Mountainscape } from "./layers/Mountainscape";
import { KreaArtLayer } from "./layers/KreaArtLayer";
import { driftSeams } from "./useSceneDrift";
import { PLANE_DEPTHS } from "./layers/Mountainscape";
import { CROSSFADE } from "../design/motion/sceneMotion";
import type { SceneMood } from "./mood";
import type { SceneArt } from "./useSceneArt";

afterEach(() => cleanup());

const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };

describe("M5 — drift/parallax STOP: reduced-motion Mountainscape == static designed pose", () => {
  it.each([DAY, NIGHT])(
    "the drifting Mountainscape under reduced-motion is BYTE-IDENTICAL to the static (no-seam) one (%o)",
    (mood) => {
      // The static designed pose (SPR-05): no seams at all.
      const staticRender = render(<Mountainscape mood={mood} />);
      const staticHtml = staticRender.container.innerHTML;
      cleanup();

      // The reduced-motion drift: identity seams (driftSeams(..., reducedMotion=true)).
      const reducedSeams = driftSeams(99_999, PLANE_DEPTHS, true);
      const reducedRender = render(<Mountainscape mood={mood} seams={reducedSeams} />);
      const reducedHtml = reducedRender.container.innerHTML;

      // Equality ⇒ the reduced state is literally the SPR-05 designed composition.
      expect(reducedHtml).toBe(staticHtml);
    },
  );

  it("a RUNNING drift, by contrast, DOES change the markup (the breath is real when not reduced)", () => {
    const staticRender = render(<Mountainscape mood={DAY} />);
    const staticHtml = staticRender.container.innerHTML;
    cleanup();
    const running = driftSeams(7_000, PLANE_DEPTHS, false);
    const runRender = render(<Mountainscape mood={DAY} seams={running} />);
    expect(runRender.container.innerHTML).not.toBe(staticHtml);
  });
});

describe("M5 — crossfade → near-instant opacity DISSOLVE under reduced-motion (opacity only)", () => {
  const liveArt: SceneArt = {
    imageUrl: "https://art/night.png",
    prevImageUrl: "https://art/day.png",
    fadeKey: 3,
    isFallback: false,
    status: "ready",
    reason: null,
  };

  it("the frozen crossfade is an opacity transition at the reduced duration — no transform, no keyframe", () => {
    const { container } = render(<KreaArtLayer art={liveArt} frozen />);
    const slots = Array.from(container.querySelectorAll<HTMLElement>("[data-krea-slot]"));
    expect(slots.length).toBeGreaterThanOrEqual(1);
    for (const s of slots) {
      // The ONE allowed animated property under reduced motion is opacity.
      expect(s.style.transition).toContain("opacity");
      expect(s.style.transition).toContain(CROSSFADE.reducedMs);
      // Forbidden under reduced motion: a transform transition or a keyframe.
      expect(s.style.transition).not.toContain("transform");
      expect(s.style.animation).toBe("");
    }
  });
});
