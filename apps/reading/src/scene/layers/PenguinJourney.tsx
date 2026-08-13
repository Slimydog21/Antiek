import type { SceneMood } from "../mood";

/**
 * PenguinJourney (SPR-04, milestone 3 — "the penguin running off into the
 * unknown").
 *
 * ─── THIS IS SCENERY, NOT THE INTERACTIVE MASCOT ─────────────────────────
 * A small brain SILHOUETTE that traverses the topography toward the horizon,
 * loops forever, and is purely decorative. It is DELIBERATELY distinct from the
 * interactive <PenguinMascot/> (SPR-05 / SPR-12):
 *
 *   | aspect      | PenguinJourney (this)        | PenguinMascot (SPR-05)        |
 *   |-------------|------------------------------|-------------------------------|
 *   | role        | scenery / atmosphere         | interactive project home      |
 *   | size        | tiny (~26px), far horizon    | large (~MASCOT_SIZE), foreground|
 *   | placement   | walks along the ridge, z-0   | roams the whole viewport      |
 *   | interaction | NONE (pointer-events-none)   | click / double-click / drag   |
 *   | look        | flat token-fill silhouette   | full <BrainMascot> mark, 5 fills |
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
          animation: "akb-penguin-journey 38s linear infinite",
          willChange: "transform",
        }}
      >
        <div
          className="h-full w-full"
          style={{ animation: "akb-penguin-bob 0.9s ease-in-out infinite" }}
        >
          {/* A compact brain silhouette — distinct, simplified, NOT the
              full BrainMascot mark. Token fills only. */}
          <svg viewBox="0 0 24 24" className="h-full w-full" focusable="false">
            {/* the two hemispheres — one rounded silhouette */}
            <path
              d="M12 2.6 C 7.9 1.3, 3.4 4, 4.3 9 C 4.9 12.7, 6.8 14.9, 8 16.9 C 8.8 18.3, 10.3 19.3, 12 18.9 C 13.7 19.3, 15.2 18.3, 16 16.9 C 17.2 14.9, 19.1 12.7, 19.7 9 C 20.6 4, 16.1 1.3, 12 2.6 Z"
              fill={coat}
            />
            {/* central sulcus */}
            <path d="M12 3.8 C 11.2 8, 12.8 13, 12 17.8" stroke={belly} strokeWidth="1" fill="none" strokeLinecap="round" />
            {/* two surface folds per hemisphere */}
            <path d="M6.4 8.4 C 7.7 7.6, 9.1 7.6, 10.3 8.5" stroke={belly} strokeWidth="1" fill="none" strokeLinecap="round" />
            <path d="M17.6 8.4 C 16.3 7.6, 14.9 7.6, 13.7 8.5" stroke={belly} strokeWidth="1" fill="none" strokeLinecap="round" />
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
