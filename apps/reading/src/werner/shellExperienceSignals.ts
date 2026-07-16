import { emitWernerExperience } from "./reactionBus";

const LOCAL_RESEARCH_PROVENANCE_TTL_MS = 10_000;
const locallyStartedResearchSessions = new Map<string, number>();
const locallyStartedResearchExpiryTimers = new Map<
  string,
  ReturnType<typeof setTimeout>
>();

export type ResearchReactionPhase =
  | "idle"
  | "running"
  | "complete"
  | "error";

export function notifyPointerIdleEdge(
  wasPointerIdle: boolean,
  isPointerIdle: boolean,
  eligible = true,
): boolean {
  if (wasPointerIdle || !isPointerIdle || !eligible) return false;
  emitWernerExperience("idle");
  return true;
}

export function notifyShellFailure(): void {
  emitWernerExperience("fail");
}

/**
 * A microphone button press is intent, not evidence that recording began.
 * Call this only after MediaRecorder.start() returns successfully so Werner
 * never performs a listening beat for denied consent or failed hardware.
 */
export function notifyVoiceRecordingStarted(): void {
  emitWernerExperience("voice_recording_started");
}

/** Call only after the first HTMLMediaElement.play() promise resolves. */
export function notifyVoicePlaybackStarted(): void {
  emitWernerExperience("voice_playback_started");
}

/** A decoded and parsed 2xx thought-partner reply is ready to be shown. */
export function notifyThoughtPartnerReplyReceived(): void {
  emitWernerExperience("thought_partner_reply_received");
}

export function notifyResearchStarted(sessionId: string): void {
  const startedAt = Date.now();
  locallyStartedResearchSessions.set(sessionId, startedAt);
  const previousTimer = locallyStartedResearchExpiryTimers.get(sessionId);
  if (previousTimer) clearTimeout(previousTimer);
  const expiryTimer = setTimeout(() => {
    // A repeated launch for the same deterministic session owns the newer
    // timestamp and timer; an older timer must not erase that provenance.
    if (locallyStartedResearchSessions.get(sessionId) === startedAt) {
      locallyStartedResearchSessions.delete(sessionId);
      locallyStartedResearchExpiryTimers.delete(sessionId);
    }
  }, LOCAL_RESEARCH_PROVENANCE_TTL_MS);
  locallyStartedResearchExpiryTimers.set(sessionId, expiryTimer);
  emitWernerExperience("deep_research_start");
}

/**
 * One-shot provenance claimed when the local monitor mounts. The short TTL is
 * a safety net for interrupted navigation: a historical reopen must not inherit
 * a launch animation merely because the original monitor never mounted.
 */
export function consumeLocallyStartedResearchSession(sessionId: string): boolean {
  const startedAt = locallyStartedResearchSessions.get(sessionId);
  locallyStartedResearchSessions.delete(sessionId);
  const expiryTimer = locallyStartedResearchExpiryTimers.get(sessionId);
  if (expiryTimer) clearTimeout(expiryTimer);
  locallyStartedResearchExpiryTimers.delete(sessionId);
  if (startedAt === undefined) return false;
  const age = Date.now() - startedAt;
  return age >= 0 && age <= LOCAL_RESEARCH_PROVENANCE_TTL_MS;
}

export function notifyResearchPhaseEdge(
  previous: ResearchReactionPhase,
  current: ResearchReactionPhase,
): boolean {
  if (previous === current || current === "idle") return false;
  // Start is an action edge emitted by the successful launch boundary. A
  // polling snapshot becoming `running` is only observation and may be a
  // remount/reconnect, so it must never replay the launch animation.
  if (current === "running") return false;
  if (current === "complete") emitWernerExperience("deep_research_complete");
  if (current === "error") emitWernerExperience("deep_research_error");
  return true;
}
