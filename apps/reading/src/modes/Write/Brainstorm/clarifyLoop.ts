/**
 * Clarify-loop state machine (specs/write/ SPR-05 M3).
 *
 * The brainstorm-interview asks clarifying questions to get context, but a
 * bounded number — the spec's mechanical gate is "a turn cap prevents
 * over-questioning." This is the pure, testable governor for that loop: it
 * counts turns and ends the loop when the agent signals completion OR the
 * cap is hit, whichever comes first. The agent wanting "one more question"
 * never overrides the cap.
 *
 * It mirrors the interviewer role's ``InterviewerResult.should_end`` signal
 * (the agent's own judgement) but makes the *cap* authoritative, so a
 * runaway agent can't loop forever.
 */

export const DEFAULT_TURN_CAP = 4;

export interface ClarifyState {
  turns: number;
  maxTurns: number;
  done: boolean;
  /** Why the loop ended: the agent finished, or the cap was hit. */
  endReason: "agent_complete" | "turn_cap" | null;
}

export function initClarify(maxTurns: number = DEFAULT_TURN_CAP): ClarifyState {
  return { turns: 0, maxTurns: Math.max(1, maxTurns), done: false, endReason: null };
}

/** Whether another clarifying question may be asked. */
export function canAskMore(state: ClarifyState): boolean {
  return !state.done && state.turns < state.maxTurns;
}

/**
 * Record one completed clarification turn. ``shouldEnd`` is the agent's own
 * judgement (InterviewerResult.should_end). The loop ends when the agent
 * is done OR the cap is reached — the cap WINS over an agent that wants to
 * keep going.
 */
export function recordTurn(
  state: ClarifyState,
  opts: { shouldEnd: boolean },
): ClarifyState {
  const turns = state.turns + 1;
  if (opts.shouldEnd) {
    return { ...state, turns, done: true, endReason: "agent_complete" };
  }
  if (turns >= state.maxTurns) {
    return { ...state, turns, done: true, endReason: "turn_cap" };
  }
  return { ...state, turns, done: false, endReason: null };
}
