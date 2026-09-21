/**
 * Brain animated pose suite (brand § 10).
 *
 * Each export is a pure SVG React component with CSS-keyframe
 * animations defined in `./animations.css` (auto-imported by every
 * pose). Reduced-motion fallbacks are baked into the same CSS file.
 *
 * Usage pattern:
 *   <BrainTobogganSpinner size={32} label="Streaming investigation…" />
 *
 * The brand bible prohibits Brain copy (§ 12 voice guidance) —
 * `label` is for screen readers only, never rendered as visible
 * text next to the pose.
 */
export { default as BrainTobogganSpinner } from "./BrainTobogganSpinner";
export { default as BrainThinking } from "./BrainThinking";
export { default as BrainCaughtAFish } from "./BrainCaughtAFish";
export { default as BrainSleeping } from "./BrainSleeping";
export { default as BrainWaddle } from "./BrainWaddle";
