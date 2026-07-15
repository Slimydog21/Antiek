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

export function notifyShellFailure(): void {
  emitWernerExperience("fail");
}

export function notifySourceReadCommitted(): void {
  emitWernerExperience("source_read_committed");
}

export function notifyOutlineBlockCommitted(): void {
  emitWernerExperience("outline_block_committed");
}

export function notifySpeakInviteCommitted(): void {
  emitWernerExperience("speak_invite_committed");
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
