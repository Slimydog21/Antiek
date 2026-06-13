/**
 * sceneMotion.ts — the living-scene motion vocabulary (ALC SPR-06 M2).
 *
 * The single source of truth for every scene timing/easing/amplitude/period.
 * It EXTENDS the `src/design/motion.ts` idiom (named tokens, each carrying the
 * FEEL it must produce + WHY the number) into the one place `motion.ts` does
 * not reach: ambient, continuous, rAF-driven scene motion (drift, parallax
 * breath) and the choreographed art crossfade.
 *
 * WHY A SEPARATE FILE (not folded into motion.ts): motion.ts is the INTERACTION
 * vocabulary — press / hover-lift / enter, all CSS-transition class strings on
 * user-triggered surfaces, all ≤ the 800ms signature-beat ceiling. The scene's
 * motion is a different KIND: ambient (no trigger), continuous (it never
 * "finishes"), and SLOW BY DESIGN (drift periods are tens of seconds — orders of
 * magnitude beyond the interaction ceiling, on purpose: weather, not a button).
 * Mixing the two would let a scene period leak into an interaction or vice versa.
 * One file per kind keeps each vocabulary coherent and the rationale legible.
 *
 * THE TWO PHYSICAL FORMS (and why each token is shaped the way it is):
 *
 *   • DURATIONS + EASINGS — the CSS-transition timings for the art crossfade and
 *     the procedural light state-transition. CSS strings ("ms" / "cubic-bezier")
 *     so they go straight into `transition`. The crossfade easings are reused
 *     from the canonical `--ease-*` token set (motion.ts ↔ tokens.css) so the
 *     scene shares the app's easing curves rather than inventing rogue ones.
 *
 *   • AMPLITUDES (px) + PERIODS (ms) — the parallax-breath drift parameters. These
 *     are NOT CSS transitions: SPR-06 drives them per-frame off the scene clock
 *     (transform/opacity only), so they are NUMBERS the drift hook reads, not
 *     class strings. Periods are deliberately LONG and mutually PRIME so the
 *     composition never visibly loops (see DRIFT_PERIODS_MS rationale).
 *
 * REDUCED-MOTION (M5): every token here has a defined reduced-motion behaviour —
 * drift/parallax amplitudes collapse to 0 (no oscillation), the crossfade
 * collapses to CROSSFADE.reducedMs (a near-instant dissolve). The motion guard
 * (motion.guard.test.ts) is extended to enforce that scene animation code sources
 * its numbers from THIS file (token-only), and the reduced-motion guard
 * (scene.css + the clock's structural freeze) enforces the collapse at runtime.
 *
 * GPU-CHEAP ONLY: every consumer animates transform / opacity. No layout props.
 */
import { motion } from "../tokens";

/* ─── CROSSFADE — the choreographed art transition (M3) ──────────────────────
 *
 * When the mood changes and new Krea art resolves, the incoming art fades UP as
 * the procedural light eases toward the new mood; the outgoing art releases.
 * INTERRUPTIBLE: a second mood change mid-fade retargets from the CURRENT opacity
 * (CSS transitions interpolate from the computed value, so a transition restarted
 * mid-flight glides from where it is — never snaps to 0 and re-runs).
 */
export const CROSSFADE = {
  /**
   * FEEL: a calm dissolve from one sky to another — slow enough to read as a
   * weather change, not a slideshow cut; fast enough that a mood flip feels
   * responsive. WHY 1200ms: longer than the interaction `slow` ceiling (800ms,
   * a button's longest flourish) because a SKY changing is a bigger, calmer
   * event than a control; 1200ms is ~the low end of "cinematic dissolve" and
   * keeps a mid-flip retarget visibly smooth (at 800ms a retarget reads as a
   * stutter; beyond ~1600ms the old sky lingers as ghosting). Tuned to sit just
   * above the interaction ceiling so the scene reads slower than the chrome.
   */
  ms: "1200ms",
  /**
   * FEEL: under reduced-motion the crossfade is a near-instant opacity dissolve
   * — present (so the swap is not a hard jump-cut that would read as a glitch)
   * but effectively immediate. WHY 1ms (not 0): a 1ms opacity transition is
   * imperceptible yet keeps the property animatable (opacity is the ONE allowed
   * animated property under reduced-motion per M5), so the e2e "allowed-
   * properties-only" assertion sees opacity and nothing else — a designed
   * dissolve, not a forbidden transform/keyframe. Mirrors motion.css's 0.01ms
   * universal collapse idiom (effectively instant, still technically a transition).
   */
  reducedMs: "1ms",
  /**
   * The incoming art's painted opacity ceiling. WHY 0.82 (not 1.0): the Krea art
   * TINTS and TEXTURES the sky; the procedural snow/cloud motion must still read
   * ON TOP of it (the living layer is the point), so the art never fully occludes
   * the floor. Pinned here (was an inline literal in KreaArtLayer) so the value
   * has one home + rationale. Unitless opacity, not a duration.
   */
  paintedOpacity: 0.82,
  /** FEEL: the incoming art eases OUT (decelerates into place) — the canonical
   *  "arriving element" curve, shared with the app's `enter`. */
  easeIn: motion.easing.enter,
  /** FEEL: the outgoing art eases on the standard interaction curve as it
   *  releases — shared with the app's `standard`, no rogue bezier. */
  easeOut: motion.easing.standard,
} as const;

/* ─── LIGHT — the procedural state-transition (M3) ───────────────────────────
 *
 * As the discrete mood crosses (day↔night) the procedural light EASES rather
 * than snapping, choreographed WITH the crossfade above (the art fades up as the
 * light eases toward the new mood's atmosphere). This is the per-mood-change
 * transition on the procedural atmosphere, distinct from the always-on phase
 * drift below.
 */
export const LIGHT = {
  /**
   * FEEL: the sky's light "turns" toward the new mood at the same calm pace the
   * art dissolves, so the two read as ONE event (light + art moving together),
   * not two staggered transitions. WHY == CROSSFADE.ms (1200ms): choreography
   * requires the light and the art to share a duration; a mismatch reads as the
   * art and the sky disagreeing about what time it is. Sourced from CROSSFADE so
   * the coupling can never silently drift apart.
   */
  ms: CROSSFADE.ms,
  /** Reduced-motion: the light snaps with the same near-instant dissolve as the
   *  crossfade (one coherent collapse). */
  reducedMs: CROSSFADE.reducedMs,
  /** FEEL: light eases on the standard curve (a natural turn, no overshoot). */
  ease: motion.easing.standard,
} as const;

/* ─── DRIFT — the parallax breath (M4) ───────────────────────────────────────
 *
 * Each depth plane drifts on a slow, subtle, INDEPENDENT oscillation — the
 * "breathing." Driven per-frame off the scene clock (transform only). The drift
 * hook (useSceneDrift.ts) reads these numbers; they are NOT CSS transitions.
 *
 * AMPLITUDES are tiny (sub-nausea, sub-legibility-impact) and scale by each
 * plane's parallax `depth` (far breathes least, near most). PERIODS are long and
 * mutually PRIME so the three planes' phases never re-align — the composition
 * never visibly "loops back to the same pose."
 */
export const DRIFT = {
  /**
   * FEEL: the deepest a near plane may travel on its breath — a barely-perceptible
   * sway, depth you feel more than see. WHY ±6px at depth 1.0: the existing
   * pointer parallax is capped at ±8px (peaks.ts MAX_PARALLAX_PX) and reads as
   * depth, not motion; the AMBIENT breath must be SMALLER than the interactive
   * parallax (ambient should never out-shout a deliberate pointer move), so 6px <
   * 8px. Scaled by plane depth, the far plane breathes ~1.8px (0.3 × 6) — sub-
   * threshold. Below ~4px the breath is invisible; above ~8px it competes with
   * reading. 6px is the tuned ceiling. PIXELS (a transform translate), not a duration.
   */
  maxAmplitudePx: 6,
  /**
   * FEEL: a vertical "settle" component to the breath, even subtler than the
   * horizontal sway (vertical motion is more noticeable to the eye, so it must
   * be smaller). WHY ±2px: a third of the horizontal max — enough to keep the
   * breath from being a flat left-right slide (which reads mechanical), small
   * enough never to nudge the horizon. Pixels.
   */
  maxAmplitudeYPx: 2,
  /**
   * The three planes' breath PERIODS in ms, far → near (index-aligned with
   * Mountainscape's PLANES). FEEL: each plane breathes at its OWN slow pace; the
   * composition never re-aligns to a repeating pose. WHY long + MUTUALLY PRIME:
   * a parallax that loops on a common period reads as a looping GIF; choosing
   * periods whose ratios are not small integers means the combined phase only
   * repeats after their least-common-multiple (~hours here), so the eye never
   * catches a loop. Values are tens of seconds (weather-slow, far beyond the
   * 800ms interaction ceiling — that is the POINT, ambient ≠ interaction). The
   * three are pairwise coprime second-counts (29s / 37s / 43s, all prime) → LCM
   * ≈ 46153 s ≈ 12.8h: no visible loop in any session. Milliseconds (a rAF period),
   * not a CSS transition duration.
   */
  periodsMs: [29_000, 37_000, 43_000] as readonly number[],
  /**
   * A second, slower vertical period per plane so the x and y breaths are out of
   * phase (a circular-ish drift, not a diagonal line). FEEL: organic settle, not
   * a ruler-straight slide. WHY a DIFFERENT prime set (31s / 41s / 47s): if x and
   * y shared a period the breath would be a straight diagonal; distinct coprime
   * periods make each plane trace a slow Lissajous figure that never repeats.
   * Milliseconds.
   */
  periodsYMs: [31_000, 41_000, 47_000] as readonly number[],
  /** Reduced-motion: ZERO amplitude — the breath stops entirely, the planes sit
   *  at their designed static pose (the SPR-05 composition IS the reduced state). */
  reducedAmplitudePx: 0,
} as const;

/* ─── PARALLAX — the interactive pointer depth (pre-existing, named here) ─────
 *
 * The pointer-driven parallax already lives in peaks.ts (MAX_PARALLAX_PX = ±8px).
 * SPR-06 does not change it, but it NAMES the relationship here so the ambient
 * DRIFT can be reasoned about against it (DRIFT.maxAmplitudePx < this cap — the
 * breath must never out-travel a deliberate pointer move). This is a reference,
 * not a second source of truth: peaks.ts remains the owner of the pointer cap.
 */
export const PARALLAX = {
  /** Mirror of peaks.ts MAX_PARALLAX_PX, restated so DRIFT's "breath < pointer"
   *  invariant is checkable in one place. The owner is peaks.ts. */
  pointerMaxPx: 8,
} as const;

/* ─── PENGUIN — the scenery penguin's journey + waddle (pre-existing; named) ──
 *
 * The scenery penguin (PenguinJourney.tsx) traverses the horizon and bobs. These
 * were inline literals (38s journey / 0.9s linear walk loop, 0.9s ease-in-out
 * bob) BEFORE SPR-06; M2 brings them into the token file so the scene's motion
 * vocabulary is complete and the token gate is genuinely 0-literal on the scene
 * surface. The keyframes themselves stay in scene.css (the sanctioned home);
 * these tokens supply the duration/easing the elements consume.
 */
export const PENGUIN = {
  /** FEEL: a long, unhurried trek toward the horizon — the penguin is barely
   *  moving, "off into the unknown." WHY 38s: a slow-enough crawl that the eye
   *  reads it as distant scenery, not a sprite racing the screen. Seconds (CSS). */
  journeyDuration: "38s",
  /** FEEL: a gentle waddle bob. WHY 0.9s: roughly a slow footstep cadence; faster
   *  reads frantic, slower reads like floating. Seconds (CSS). */
  bobDuration: "0.9s",
  /** The walk loops at constant speed (no ease — a steady trek). */
  journeyEase: "linear",
  /** The bob eases symmetrically (a natural up-down settle). */
  bobEase: "ease-in-out",
} as const;

/** Numeric ms helpers for JS timers / rAF maths matched to a scene beat — the
 *  same convenience `motion.ts` exposes via `durationMs`, parsed from the CSS
 *  strings so there is exactly one source of truth (the CSS strings above). */
export const sceneDurationMs = {
  crossfade: Number.parseInt(CROSSFADE.ms, 10),
  crossfadeReduced: Number.parseInt(CROSSFADE.reducedMs, 10),
  light: Number.parseInt(LIGHT.ms, 10),
} as const;
