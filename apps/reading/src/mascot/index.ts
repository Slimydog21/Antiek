/**
 * Brain steering + choreography engine (SPR-05 / SPR-10).
 *
 * The public surface the mascot (and tests) consume. One mascot, one
 * position, one reduced-motion guard — this module is the STEERING + EMOTE
 * layer that rides on the mascot's existing machinery (MascotStation.tsx), it
 * does not fork a second mascot.
 *
 *   mascotState  — the pure state machine (idle/following/waddling/emoting/frozen)
 *   MascotStage  — the imperative command controller (the SPR-10 seam)
 *   useMouseFollow — the live/idle cursor read seam (read-only ref; feeds the
 *                  bait + line their `live`/`pointerIdle`/`tabHidden` signals)
 *   emotes       — the emote vocabulary mapped onto existing animated marks
 *   choreography — the PRODUCT_ACTIVATE → waddle-to-control listener (SPR-10),
 *                  plus the opt-in `data-mascot-target` click path (SPR-10 M4)
 *   (the walk-cycle rig and the cursor-bait line were removed 2026-08-13)
tegrator + reel/roam constants) was removed
 * with the 2026-07-02 fixed-station rework — Brain no longer chases the cursor;
 * see docs/htmlspec/werner-fixed-station/DESIGN.md.
 */

export {
  mascotReducer,
  isBusy,
  INITIAL_MASCOT_STATE,
  // SPR-05 — the endless fishing loop (the Scrat cycle).
  shouldFish,
  fishingStep,
  FISHING_BEATS,
  FISHING_CYCLE_MS,
  type MascotState,
  type MascotStateName,
  type MascotEvent,
  type AmbientState,
  type FishingBeat,
  type FishingBeatStep,
  type FishingFrame,
} from "./mascotState";

export {
  createMascotStage,
  WADDLE_MS,
  type StageHost,
  type MascotStageController,
} from "./MascotStage";

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
  MASCOT_TARGET_ATTR,
  type ChoreographyOptions,
  type TargetChoreographyOptions,
} from "./choreography";

export {
  emoteForExperience,
  emitMascotExperience,
  installReactionBus,
  isProductExperience,
  PRODUCT_EXPERIENCES,
  MASCOT_EXPERIENCE_EVENT,
  type ProductExperience,
  type ReactionBusOptions,
  type MascotExperienceDetail,
} from "./reactionBus";

export {
  consumeLocallyStartedResearchSession,
  notifyPointerIdleEdge,
  notifyResearchPhaseEdge,
  notifyResearchStarted,
  notifyShellFailure,
  notifyVoicePlaybackStarted,
  type ResearchReactionPhase,
} from "./shellExperienceSignals";


// SPR-01 — the station-activity surface. Importing this registers the built-in
// activities (rest self-registers as the default); consumers read the
// active activity through these accessors instead of hard-coding one.
export {
  registerActivity,
  getActivity,
  listActivities,
  getDefaultActivity,
  restActivity,
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
