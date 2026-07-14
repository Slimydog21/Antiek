/**
 * Werner animated pose suite (brand § 10).
 *
 * Each export is a React pose composition—canonical raster identity with
 * code-native props where needed—and uses CSS keyframes from `animations.css`.
 * Reduced-motion fallbacks are baked into the same CSS file.
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
export { default as WernerWaking } from "./WernerWaking";
export { default as WernerDuskGaze } from "./WernerDuskGaze";
export { default as WernerNightWatch } from "./WernerNightWatch";
export { default as WernerWaddle } from "./WernerWaddle";
