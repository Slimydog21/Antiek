/**
 * Werner steering + choreography engine (SPR-05 / SPR-10).
 *
 * The public surface the mascot (and tests) consume. One penguin, one
 * position, one roam loop, one reduced-motion guard — this module is the
 * STEERING + EMOTE layer that rides on the mascot's existing machinery
 * (PenguinMascot.tsx), it does not fork a second penguin.
 *
 *   wernerState  — the pure state machine (idle/following/waddling/emoting/frozen)
 *   WernerStage  — the imperative command controller (the SPR-10 seam)
 *   useMouseFollow — the ~0.5s-lagged cursor pursuit (read-only ref seam)
 *   emotes       — the emote vocabulary mapped onto existing animated marks
 *   choreography — the PRODUCT_ACTIVATE → waddle-to-control listener (SPR-10),
 *                  plus the opt-in `data-werner-target` click path (SPR-10 M4)
 *   WernerRig    — the vector WALK-CYCLE rig (SPR-06 M1): feet + flippers that
 *                  animate off the existing walk signal (no second motion source)
 */

export {
  wernerReducer,
  isBusy,
  INITIAL_WERNER_STATE,
  type WernerState,
  type WernerStateName,
  type WernerEvent,
  type AmbientState,
} from "./wernerState";

export {
  createWernerStage,
  WADDLE_MS,
  type StageHost,
  type WernerStageController,
} from "./WernerStage";

export {
  useMouseFollow,
  LAG_MS,
  SAMPLE_INTERVAL_MS,
  FOLLOW_EASE,
  POINTER_IDLE_MS,
  centerLaggedTarget,
  type MouseFollow,
  type FollowReading,
  type UseMouseFollowOptions,
} from "./useMouseFollow";

export { wernerIceFishingCursor } from "./iceFishingFlags";
export { WernerIceBait } from "./WernerIceBait";
export { WernerIceCursorShell } from "./WernerIceCursorShell";

export {
  EmoteView,
  EMOTE_KINDS,
  EMOTE_DURATION_MS,
  emoteDurationMs,
  type EmoteKind,
} from "./emotes";

export {
  installChoreography,
  installTargetChoreography,
  productSelector,
  WERNER_TARGET_ATTR,
  type ChoreographyOptions,
  type TargetChoreographyOptions,
} from "./choreography";

export { default as WernerRig, type WernerRigProps } from "./WernerRig";
