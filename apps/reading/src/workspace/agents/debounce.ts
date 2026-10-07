/**
 * agents/debounce.ts — SPR-10 M2: herdr's status debounce as a PURE reducer
 * (refs/omarchy-herdr.md R19, herdr/src/pane/agent_detection.rs:5-13):
 * working→idle needs 3 confirmations 100 ms apart, capped at 700 ms;
 * 3 s startup grace. The clock is the caller's (`at`), so tests pin the
 * exact thresholds without timers.
 *
 * Only the step OUT of working is debounced (herdr debounces only
 * working→idle). First observations and every transition INTO working
 * commit at once; `blocked` is not a phase here: `needsInput` bypasses the
 * reducer and the store commits it at t=0.
 *
 * Recorded limit (handoff §6.2): against a 2 s list poll the three confirms
 * re-read one snapshot and commit at +300 ms, so the reducer is near-
 * vacuous today; the thresholds are what the tests pin.
 */
import type { Phase } from "./agentStatus";

export const DEBOUNCE = Object.freeze({
  confirmations: 3,
  intervalMs: 100,
  capMs: 700,
  startupGraceMs: 3000,
  pollMs: 2000,
  idlePollMs: 30000,
});

export type DebounceState =
  | { kind: "settled"; phase: Phase }
  | { kind: "confirming"; from: "working"; candidate: Phase; startedAt: number; agreed: number };

export interface DebounceObservation {
  phase: Phase;
  at: number;
  source: "poll" | "confirm";
}

export interface DebounceResult {
  next: DebounceState;
  /** The phase to commit now, or null to hold. */
  commit: Phase | null;
  /** When the next confirmation should be read, or null. */
  confirmAt: number | null;
}

const settled = (phase: Phase): DebounceState => ({ kind: "settled", phase });

export function debounceStep(state: DebounceState | undefined, obs: DebounceObservation): DebounceResult {
  const { phase, at } = obs;
  if (state === undefined) return { next: settled(phase), commit: phase, confirmAt: null };

  if (state.kind === "settled") {
    if (state.phase === phase) return { next: state, commit: null, confirmAt: null };
    if (phase === "working" || state.phase !== "working") return { next: settled(phase), commit: phase, confirmAt: null };
    // working → finished|unknown: open the confirmation window.
    return {
      next: { kind: "confirming", from: "working", candidate: phase, startedAt: at, agreed: 1 },
      commit: null,
      confirmAt: at + DEBOUNCE.intervalMs,
    };
  }

  // confirming
  if (at >= state.startedAt + DEBOUNCE.capMs) return { next: settled(phase), commit: phase, confirmAt: null };
  if (phase === "working") return { next: settled("working"), commit: null, confirmAt: null };
  const commitNotBefore = state.startedAt + DEBOUNCE.confirmations * DEBOUNCE.intervalMs;
  if (phase === state.candidate) {
    const agreed = state.agreed + 1;
    if (agreed > DEBOUNCE.confirmations && at >= commitNotBefore) return { next: settled(phase), commit: phase, confirmAt: null };
    const next: DebounceState = { ...state, agreed };
    // Enough agreement but too early: wait for the floor itself, not another interval.
    const confirmAt = Math.min(agreed > DEBOUNCE.confirmations ? commitNotBefore : at + DEBOUNCE.intervalMs, state.startedAt + DEBOUNCE.capMs);
    return { next, commit: null, confirmAt };
  }
  // A different non-working candidate: restart agreement, keep the cap anchor.
  return {
    next: { ...state, candidate: phase, agreed: 1 },
    commit: null,
    confirmAt: Math.min(at + DEBOUNCE.intervalMs, state.startedAt + DEBOUNCE.capMs),
  };
}

export function inStartupGrace(startedAt: number, now: number): boolean {
  return now - startedAt < DEBOUNCE.startupGraceMs;
}
