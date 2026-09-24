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
 * PRESS + HOVER-LIFT — the tactile pair for a raised surface that carries
 * the diagonal hard shadow (`shadow-z1`, 3px 3px): hover lifts it half a
 * pixel up-left and grows the shadow half a pixel; press sinks it half a
 * pixel and shrinks the shadow by the same. The shadow's far corner never
 * moves (design spec §4, PostHog's conserved press): transform AND
 * box-shadow transition together on one duration and easing, so the sum
 * of offset and shadow is constant on every frame. The old recipe
 * transitioned transform only and jumped the shadow to 8px on the first
 * hover frame (footprint +3 -> +8 -> +6 -> +2 px, measured in Chromium).
 * Press runs on duration-fast (80ms), hover on duration-base (150ms).
 *
 * LemonButton no longer uses this: its keycap (a vertical frame, the
 * same conservation) lives in components/lemon/lemon.css. This string
 * serves the cards, cartridges and handles that keep the diagonal shadow.
 * Assumes a base `shadow-z1 dark:shadow-z1-night` on the element.
 */
export const press =
  "transition-[transform,box-shadow] duration-base active:duration-fast ease-standard " +
  "hover:-translate-x-[0.5px] hover:-translate-y-[0.5px] " +
  "hover:shadow-[3.5px_3.5px_0_0_var(--fixed-ink)] dark:hover:shadow-[3.5px_3.5px_0_0_var(--sun-deep)] " +
  "active:translate-x-[0.5px] active:translate-y-[0.5px] " +
  "active:shadow-[2.5px_2.5px_0_0_var(--fixed-ink)] dark:active:shadow-[2.5px_2.5px_0_0_var(--sun-deep)]";

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
 * Wired: LemonModal — the dialog rises as it arrives. Panels/windows use
 * the framer `surfaceSpring` below instead (they already animate scale +
 * opacity through framer-motion, so a second CSS enter would fight it).
 */
export const enter =
  "transition-[opacity,transform] duration-base ease-enter " +
  "data-[enter=false]:opacity-0 data-[enter=false]:translate-y-1 " +
  "data-[enter=true]:opacity-100 data-[enter=true]:translate-y-0";

/**
 * SURFACE-SPRING — the one framer-motion spring for the "a surface
 * arrives" gesture (floating panels, workspace windows). Was hand-tuned
 * per layer (320/28 vs 320/30 — audit 01); one spec consumed by both so
 * interaction physics can't diverge again. Callers still gate it behind
 * their reduced-motion check (`reduceMotion ? { duration: 0 } : …`).
 */
export const surfaceSpring = {
  type: "spring",
  stiffness: 320,
  damping: 30,
} as const;

/** Duration tokens in ms (numbers), for JS timers matched to a beat. */
export const durationMs = {
  fast: Number.parseInt(motion.duration.fast, 10),
  base: Number.parseInt(motion.duration.base, 10),
  slow: Number.parseInt(motion.duration.slow, 10),
} as const;
