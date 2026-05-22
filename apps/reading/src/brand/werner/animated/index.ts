/**
 * Werner animated pose suite (brand § 10).
 *
 * Each export is a pure SVG React component with CSS-keyframe
 * animations defined in `./animations.css` (auto-imported by every
 * pose). Reduced-motion fallbacks are baked into the same CSS file.
 *
 * Usage pattern:
 *   <WernerTobogganSpinner size={32} label="Streaming investigation…" />
 *
 * The brand bible prohibits Werner copy (§ 12 voice guidance) —
 * `label` is for screen readers only, never rendered as visible
 * text next to the pose.
 */
export { default as WernerTobogganSpinner } from "./WernerTobogganSpinner";
export { default as WernerThinking } from "./WernerThinking";
export { default as WernerCaughtAFish } from "./WernerCaughtAFish";
export { default as WernerSleeping } from "./WernerSleeping";
export { default as WernerWaddle } from "./WernerWaddle";
