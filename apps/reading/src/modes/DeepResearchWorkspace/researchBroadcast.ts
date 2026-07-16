import { TERMINAL_STATES, type ResearchRunState } from "../../api/research";

export interface ResearchBroadcastSnapshot {
  investigationId: string;
  subQuestion: string;
  state: ResearchRunState;
}

export type ResearchBroadcastKind =
  "arrived" | "failed" | "stopped" | "budget_halted";

export interface ResearchBroadcast extends ResearchBroadcastSnapshot {
  kind: ResearchBroadcastKind;
}

export type ResearchStateBaseline = ReadonlyMap<string, ResearchRunState>;

export function researchStateBaseline(
  snapshots: readonly ResearchBroadcastSnapshot[],
): Map<string, ResearchRunState> {
  return new Map(
    snapshots.map((snapshot) => [snapshot.investigationId, snapshot.state]),
  );
}

/**
 * Derive presentation events from two authoritative poll snapshots.
 * Initial terminal rows are deliberately only baseline: an arrival exists
 * when this mounted episode observed non-terminal state first.
 */
export function deriveResearchBroadcasts(
  previous: ResearchStateBaseline,
  current: readonly ResearchBroadcastSnapshot[],
): ResearchBroadcast[] {
  const broadcasts: ResearchBroadcast[] = [];
  for (const snapshot of current) {
    const priorState = previous.get(snapshot.investigationId);
    if (
      priorState === undefined ||
      TERMINAL_STATES.has(priorState) ||
      !TERMINAL_STATES.has(snapshot.state)
    ) {
      continue;
    }
    broadcasts.push({
      ...snapshot,
      kind: broadcastKind(snapshot.state),
    });
  }
  return broadcasts;
}

function broadcastKind(state: ResearchRunState): ResearchBroadcastKind {
  if (state === "done") return "arrived";
  if (state === "failed") return "failed";
  if (state === "budget_halted") return "budget_halted";
  return "stopped";
}
