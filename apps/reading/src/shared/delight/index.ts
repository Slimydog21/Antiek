/**
 * shared/delight — the signature delight beats (U-05 M2).
 *
 * One reusable primitive (useCelebrate + CelebrateBurst) that every
 * product's payoff moment adopts, so the four beats are one mechanism, not
 * four bespoke animations. The only beat wired in this run is
 * research-starts (StartResearch); the other three are filed for their
 * product surfaces in src/design/motion/README.md.
 */
export { default as CelebrateBurst } from "./CelebrateBurst";
export { useCelebrate } from "./useCelebrate";
export type { CelebrateState } from "./useCelebrate";
