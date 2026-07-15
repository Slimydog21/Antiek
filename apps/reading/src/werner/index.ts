/**
 * Werner steering + choreography engine (SPR-05 / SPR-10).
 *
 * The public surface the mascot (and tests) consume. One penguin, one
 * position, one reduced-motion guard — this module is the STEERING + EMOTE
 * layer that rides on the mascot's existing machinery (PenguinMascot.tsx), it
 * does not fork a second penguin.
 *
 *   wernerState  — the pure state machine (idle/following/waddling/emoting/frozen)
 *   WernerStage  — the imperative command controller (the SPR-10 seam)
 *   useMouseFollow — the live/idle cursor read seam (read-only ref; feeds the
 *                  bait + line their `live`/`pointerIdle`/`tabHidden` signals)
 *   emotes       — the emote vocabulary mapped onto existing animated marks
 *   choreography — the PRODUCT_ACTIVATE → waddle-to-control listener (SPR-10),
 *                  plus the opt-in `data-werner-target` click path (SPR-10 M4)
 *   WernerRig    — the vector WALK-CYCLE rig (SPR-06 M1): feet + flippers that
 *                  animate off the existing walk signal (no second motion source)
 *
 * The WERNER-ICE reel (pursuit integrator + reel/roam constants) was removed
 * with the 2026-07-02 fixed-station rework — Werner no longer chases the cursor;
 * see docs/htmlspec/werner-fixed-station/DESIGN.md.
 */

export {
  wernerReducer,
  isBusy,
  INITIAL_WERNER_STATE,
  // SPR-05 — the endless fishing loop (the Scrat cycle).
  shouldFish,
  fishingStep,
  FISHING_BEATS,
  FISHING_CYCLE_MS,
  type WernerState,
  type WernerStateName,
  type WernerEvent,
  type AmbientState,
  type FishingBeat,
  type FishingBeatStep,
  type FishingFrame,
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

export {
  wernerIceFishingCursor,
  wernerArcade,
} from "./iceFishingFlags";
export { WernerIceBait } from "./WernerIceBait";
export { WernerFishingLayer } from "./WernerFishingLayer";
export { WernerIceCursorShell } from "./WernerIceCursorShell";
export { catenaryPath, rodTipFromMascotRect } from "./fishingLineGeometry";

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

export {
  emoteForExperience,
  emitWernerExperience,
  installReactionBus,
  isProductExperience,
  PRODUCT_EXPERIENCES,
  WERNER_EXPERIENCE_EVENT,
  type ProductExperience,
  type ReactionBusOptions,
  type WernerExperienceDetail,
} from "./reactionBus";

export {
  consumeLocallyStartedResearchSession,
  notifyPointerIdleEdge,
  notifyResearchPhaseEdge,
  notifyResearchStarted,
  notifyShellFailure,
  type ResearchReactionPhase,
} from "./shellExperienceSignals";

export { default as WernerRig, type WernerRigProps } from "./WernerRig";

// SPR-01 — the station-activity surface. Importing this registers the built-in
// activities (ice-fishing self-registers as the default); the mascot + shell
// render "the active (default) activity" through these accessors instead of
// hard-coding the fishing behavior.
export {
  registerActivity,
  getActivity,
  listActivities,
  getDefaultActivity,
  iceFishingActivity,
  researchLensActivity,
  activityIdForPathname,
  getActivityForPathname,
  type ActivityId,
  type ActivityUnlock,
  type CursorInstrument,
  type CursorInstrumentProps,
  type InstrumentSeamField,
  type StationActivity,
} from "./activities";

export { useStationActivity } from "./useStationActivity";
export { ResearchLensCursor } from "./ResearchLensCursor";
