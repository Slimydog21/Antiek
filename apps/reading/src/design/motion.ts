/**
 * motion.ts — the shared base-interaction vocabulary (U-05 M1).
 *
 * Three primitives, each a canonical Tailwind class string, so the
 * Lemon press / hover-lift / enter feel the same everywhere instead of
 * being re-improvised per surface. These systematize what LemonButton
 * and BookCard already do — the offset-shadow press, the −2px lift +
 * shadow grow — onto the motion tokens (duration-fast/base, motion.ts ↔
 * tokens.css ↔ tailwind.config.js).
 *
 * GPU-cheap only: transform + box-shadow + opacity. No width/height/top
 * animation, no layout thrash. Reduced-motion is honoured by the
 * Tailwind `transition-*` utilities collapsing under the OS setting via
 * the media query in motion.css; with motion off these classes still
 * apply the final state (the lift/press is instant, never lost).
 *
 * Re-export of the timing tokens for any TS that needs a duration in JS
 * (e.g. a setTimeout matched to a beat) rather than a class.
 */
import { motion } from "./tokens";

/**
 * PRESS + HOVER-LIFT — the tactile pair for a raised, fill-variant Lemon
 * surface: a −2px diagonal lift + shadow grow on hover, snapping into its
 * own shadow on :active so a tap reads as a physical press. This is
 * LemonButton's existing behaviour, pinned to one transition (the
 * `duration-base` transform) so hover and press share a single, coherent
 * timing rather than two competing `transition-duration` declarations.
 * Assumes a base `shadow-z1` on the element; lifts to `shadow-z3`.
 *
 * Kept as one string because hover and press both animate `transform`:
 * declaring the transition once (here) is correct; declaring it twice
 * (separate press/lift strings on the same element) lets the later
 * `transition-duration` silently win for both states.
 */
export const press =
  "transition-transform duration-base ease-standard " +
  "hover:-translate-x-[2px] hover:-translate-y-[2px] " +
  "hover:shadow-z3 dark:hover:shadow-z3-night " +
  "active:translate-x-[2px] active:translate-y-[2px] active:!shadow-none";

/**
 * CARD-LIFT — the gentler upward nudge for a card whose hover is led by
 * a parent `group` (BookCard's cover). Smaller travel than `press` so a
 * grid of cards lifts subtly, not like a row of buttons. Assumes the
 * element sits inside `.group` and carries a base `shadow-z1`.
 */
export const cardLift =
  "transition-transform duration-base ease-standard " +
  "group-hover:-translate-y-0.5 group-hover:shadow-z2 dark:group-hover:shadow-z2-night";

/**
 * ENTER — a panel/modal arriving: fade + a small rise, eased-out. Drive
 * it with a `data-enter` attribute the surface sets once mounted, so the
 * transition runs from the off state to the on state exactly once. The
 * keyframe-free form (transition, not animation) keeps it inside the
 * motion system and out of the anti-noise guard's keyframe net.
 *
 * Provided for panel/modal adoption; not yet wired to a consumer in this run
 * (`press` + `cardLift` are the wired primitives — LemonButton / BookCard).
 */
export const enter =
  "transition-[opacity,transform] duration-base ease-enter " +
  "data-[enter=false]:opacity-0 data-[enter=false]:translate-y-1 " +
  "data-[enter=true]:opacity-100 data-[enter=true]:translate-y-0";

/** Duration tokens in ms (numbers), for JS timers matched to a beat. */
export const durationMs = {
  fast: Number.parseInt(motion.duration.fast, 10),
  base: Number.parseInt(motion.duration.base, 10),
  slow: Number.parseInt(motion.duration.slow, 10),
} as const;
