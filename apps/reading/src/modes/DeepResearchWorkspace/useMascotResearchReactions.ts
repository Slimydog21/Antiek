import { useEffect, useRef } from "react";

import type { ResearchRunState } from "../../api/research";
import {
  consumeLocallyStartedResearchSession,
  notifyResearchPhaseEdge,
  type ResearchReactionPhase,
} from "../../mascot";
import type { SessionParentState } from "./useResearchSession";

export interface ResearchReactionSnapshot {
  sessionId: string;
  loading: boolean;
  allTerminal: boolean;
  error: string | null;
  researchStates: readonly ResearchRunState[];
  parent: SessionParentState;
}

export function deriveResearchReactionPhase({
  allTerminal,
  error,
  researchStates,
  parent,
}: ResearchReactionSnapshot): ResearchReactionPhase {
  if (error) return "error";
  if (parent.kind === "synthesis_failed" || parent.kind === "failed") return "error";
  if (
    researchStates.some(
      (state) => state === "failed" || state === "budget_halted",
    )
  )
    return "error";
  if (allTerminal && researchStates.length > 0) {
    if (researchStates.every((state) => state === "done")) {
      // Leaf DONE is not session success: only the parent's affirmed
      // completion is. A pending parent is still synthesizing; an unknown one
      // claims nothing.
      if (parent.kind === "complete") return "complete";
      return parent.kind === "pending" ? "running" : "idle";
    }
    // A wholly/mixed stopped session is terminal but neither success nor
    // failure. Staying idle avoids claiming an outcome the user cancelled.
    return "idle";
  }
  if (researchStates.length > 0) return "running";
  return "idle";
}

export function useMascotResearchReactions(
  snapshot: ResearchReactionSnapshot,
): void {
  const phase = deriveResearchReactionPhase(snapshot);
  const previousRef = useRef<{
    sessionId: string;
    phase: ResearchReactionPhase;
    observed: boolean;
    localLaunch: boolean;
  } | null>(null);

  useEffect(() => {
    const previous = previousRef.current;
    if (!previous) {
      // Claim provenance at monitor mount, not after an arbitrarily slow poll.
      // The ref carries it across loading without leaving module-global state.
      const localLaunch = consumeLocallyStartedResearchSession(
        snapshot.sessionId,
      );
      const observed = !snapshot.loading;
      if (observed && localLaunch) {
        notifyResearchPhaseEdge("running", phase);
      }
      previousRef.current = {
        sessionId: snapshot.sessionId,
        phase,
        observed,
        localLaunch: localLaunch && !observed,
      };
      return;
    }
    if (previous.sessionId !== snapshot.sessionId) {
      // useResearchSession still exposes the old session for one render before
      // its effect installs the new loading placeholder. Ignore that stale
      // frame and wait for the first non-loading snapshot of the new identity.
      previousRef.current = {
        sessionId: snapshot.sessionId,
        phase,
        observed: false,
        localLaunch: consumeLocallyStartedResearchSession(snapshot.sessionId),
      };
      return;
    }
    if (snapshot.loading) return;
    if (!previous.observed) {
      if (previous.localLaunch) {
        notifyResearchPhaseEdge("running", phase);
      }
      previousRef.current = {
        sessionId: snapshot.sessionId,
        phase,
        observed: true,
        localLaunch: false,
      };
      return;
    }
    notifyResearchPhaseEdge(previous.phase, phase);
    previousRef.current = { ...previous, phase };
  }, [phase, snapshot.loading, snapshot.sessionId]);
}
