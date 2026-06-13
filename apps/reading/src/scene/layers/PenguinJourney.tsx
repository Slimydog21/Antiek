import type { SceneMood } from "../mood";
import { PENGUIN } from "../../design/motion/sceneMotion";

/**
 * PenguinJourney (SPR-04, milestone 3 — "the penguin running off into the
 * unknown").
 *
 * ─── THIS IS SCENERY, NOT THE INTERACTIVE MASCOT ─────────────────────────
 * A small penguin SILHOUETTE that traverses the topography toward the horizon,
 * loops forever, and is purely decorative. It is DELIBERATELY distinct from the
 * interactive <PenguinMascot/> (SPR-05 / SPR-12):
 *
 *   | aspect      | PenguinJourney (this)        | PenguinMascot (SPR-05)        |
 *   |-------------|------------------------------|-------------------------------|
 *   | role        | scenery / atmosphere         | interactive project home      |
 *   | size        | tiny (~26px), far horizon    | large (~MASCOT_SIZE), foreground|
 *   | placement   | walks along the ridge, z-0   | roams the whole viewport      |
 *   | interaction | NONE (pointer-events-none)   | click / double-click / drag   |
 *   | look        | flat token-fill silhouette   | full <Werner> mark, 5 fills   |
 *
 * A maintainer must NOT merge these or wire interactivity here — see the
 * matrix above and the SPR-05 mascot contract. This penguin never reacts; it
 * only journeys.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * MOTION: a CSS keyframe walks it left→right across the lower-third horizon and
 * loops; a subtle vertical bob suggests a waddle. CSS animation (not the rAF
 * clock) keeps it cheap and lets it pause for free under reduced-motion via the
 * `motion-reduce:` variant (no JS). It shrinks slightly as it nears the
 * horizon edge, reinforcing "into the unknown".
 *
 * COLOUR: token fills only (werner-coat / werner-belly via CSS vars) — no hex.
 */

export interface PenguinJourneyProps {
  mood: SceneMood;
}

export function PenguinJourney({ mood }: PenguinJourneyProps) {
  const night = mood.dayPart === "night" || mood.dayPart === "dusk";
  // A scenery silhouette reads as a darker shape by day, a faint one by night.
  const coat = night ? "var(--werner-coat)" : "var(--shadow-2)";
  const belly = "var(--werner-belly)";

  return (
    <div
      className="pointer-events-none absolute inset-x-0 bottom-0 h-1/3 overflow-hidden"
      data-testid="penguin-journey"
      data-scenery="true"
      aria-hidden="true"
    >
      {/* The traversing wrapper — CSS-animated across the horizon, paused under
          reduced-motion (motion-reduce variant sets the animation to none). */}
      <div
        className="absolute bottom-[18%] h-7 w-7 motion-reduce:!animate-none"
        style={{
          // Timing/easing sourced from the scene motion vocabulary (M2), not
          // inline literals — see src/design/motion/sceneMotion.ts (PENGUIN).
          animation: `akb-penguin-journey ${PENGUIN.journeyDuration} ${PENGUIN.journeyEase} infinite`,
          willChange: "transform",
        }}
      >
        <div
          className="h-full w-full"
          style={{
            animation: `akb-penguin-bob ${PENGUIN.bobDuration} ${PENGUIN.bobEase} infinite`,
          }}
        >
          {/* A compact penguin silhouette — distinct, simplified, NOT the
              full Werner mark. Token fills only. */}
          <svg viewBox="0 0 24 24" className="h-full w-full" focusable="false">
            {/* body */}
            <ellipse cx="12" cy="14" rx="6" ry="8" fill={coat} />
            {/* belly */}
            <ellipse cx="12" cy="15" rx="3.4" ry="5.6" fill={belly} />
            {/* head */}
            <circle cx="12" cy="6" r="4" fill={coat} />
            {/* bill */}
            <path d="M12 6 l3 1.4 -3 1.4 z" fill="var(--werner-bill)" />
            {/* feet */}
            <path d="M9 21 l-2 1.4 3 0 z" fill="var(--werner-foot)" />
            <path d="M15 21 l2 1.4 -3 0 z" fill="var(--werner-foot)" />
          </svg>
        </div>
      </div>

      {/* The walk (akb-penguin-journey) drifts the penguin across the horizon
          and shrinks it ("into the unknown"); the bob (akb-penguin-bob) is a
          tiny waddle. Both keyframes + the reduced-motion guard that stops them
          live in src/scene/scene.css (the scene's consolidated motion home). */}
    </div>
  );
}

export default PenguinJourney;
