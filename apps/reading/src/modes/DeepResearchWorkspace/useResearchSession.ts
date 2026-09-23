/**
 * DRW SPR-09 M4 — live session consumption + reconnect.
 *
 * Polls SPR-06's durable `GET /research/sessions/{id}` (status + cost) on an
 * interval, stopping once every research is terminal and the session parent
 * is no longer pending (see `SessionParentState`). Polling — not an
 * EventSource — is the deliberate choice: it matches the codebase's dominant
 * live-update idiom (setInterval + cancellation), and because each poll
 * re-derives authoritative state from the durable endpoint (which itself
 * falls back to `reconstruct_session` from the event log), "reconnect and
 * resume" is free and gap-free — a dropped poll or a server restart simply
 * resolves on the next tick. The richer per-step SSE stream
 * (`sessionStreamUrl`) is a future EventSource upgrade; the monitor does not
 * depend on it. Snapshots are whole-state (not appended deltas), so there is
 * nothing to dedup.
 */

import { useEffect, useRef, useState } from "react";

import {
  getSession,
  TERMINAL_STATES,
  type ResearchStatus,
  type HardCeilingSnapshot,
  type SessionCost,
  type SessionStatus,
} from "../../api/research";
import type { ResearchSourcePolicy } from "../../lib/api";

/**
 * The session PARENT's outcome, which leaf states cannot tell you: every leaf
 * can be DONE while join/merge or the synthesis tail failed. Only the
 * backend's `deep_research_complete === true` is success; anything the
 * response does not affirm is `unknown`, never success.
 */
export type SessionParentState =
  | { kind: "complete" }
  | { kind: "synthesis_failed"; error: string }
  /** The backend says not complete yet and records no failure. */
  | { kind: "pending" }
  /** Recovered session (null) or a response without the field. */
  | { kind: "unknown" };

export function deriveSessionParent(s: SessionStatus): SessionParentState {
  const error = s.synthesis_tail_error?.trim();
  if (error) return { kind: "synthesis_failed", error };
  if (s.deep_research_complete === true) return { kind: "complete" };
  if (s.deep_research_complete === false) return { kind: "pending" };
  return { kind: "unknown" };
}

// Backoff ceiling while leaves are terminal but the parent is still pending
// (the synthesis tail can run for minutes, and a path that skips the tail
// never settles).
const PARENT_PENDING_MAX_INTERVAL_MS = 30_000;

export interface SessionView {
  researches: ResearchStatus[];
  cost: SessionCost | null;
  hardCeiling: HardCeilingSnapshot | null;
  live: boolean;
  allTerminal: boolean;
  parent: SessionParentState;
  loading: boolean;
  sourcePolicy: ResearchSourcePolicy[];
  sourcePolicyExecution: "metadata_only" | "runner_consumed" | null;
  /** Transient poll error; the hook keeps retrying (reconnect). */
  error: string | null;
}

const EMPTY: SessionView = {
  researches: [],
  cost: null,
  hardCeiling: null,
  live: false,
  allTerminal: false,
  parent: { kind: "unknown" },
  loading: true,
  sourcePolicy: [],
  sourcePolicyExecution: null,
  error: null,
};

export function useResearchSession(
  sessionId: string | null,
  opts: { intervalMs?: number } = {},
): SessionView {
  const [view, setView] = useState<SessionView>(EMPTY);
  const timerRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!sessionId) {
      setView(EMPTY);
      return;
    }
    let cancelled = false;
    const interval = opts.intervalMs ?? 1500;
    let terminalEvidencePolls = 0;
    let parentPendingPolls = 0;
    setView({ ...EMPTY, loading: true });

    const poll = async () => {
      try {
        const s = await getSession(sessionId);
        if (cancelled) return;
        const allTerminal =
          (s.all_terminal ?? s.researches.every((r) => TERMINAL_STATES.has(r.state))) &&
          s.researches.length > 0;
        const parent = deriveSessionParent(s);
        setView({
          researches: s.researches,
          cost: s.cost ?? null,
          hardCeiling: s.hard_ceiling ?? null,
          live: s.live,
          allTerminal,
          parent,
          loading: false,
          sourcePolicy: s.source_policy ?? [],
          sourcePolicyExecution: s.source_policy_execution ?? null,
          error: null,
        });
        // Keep polling until every research is terminal; then stop (the
        // monitor shows the final state, no wasted requests).
        const evidenceFinal =
          !s.hard_ceiling ||
          (s.hard_ceiling.run_state === "closed_reconciled" &&
            s.hard_ceiling.unknown_outcome_count === 0);
        if (!allTerminal) {
          terminalEvidencePolls = 0;
          parentPendingPolls = 0;
          timerRef.current = window.setTimeout(poll, interval);
        } else if (parent.kind === "pending") {
          // Leaves are done but the parent has neither completed nor failed:
          // the synthesis tail may still be running, and a tail failure lands
          // only after this point. Keep watching, backing off.
          parentPendingPolls += 1;
          timerRef.current = window.setTimeout(
            poll,
            Math.min(interval * 2 ** (parentPendingPolls - 1), PARENT_PENDING_MAX_INTERVAL_MS),
          );
        } else if (!evidenceFinal && terminalEvidencePolls < 3) {
          terminalEvidencePolls += 1;
          timerRef.current = window.setTimeout(
            poll,
            interval * 2 ** (terminalEvidencePolls - 1),
          );
        }
      } catch (e) {
        if (cancelled) return;
        // Transient failure → surface it but keep retrying (reconnect).
        setView((v) => ({ ...v, loading: false, error: errMessage(e) }));
        timerRef.current = window.setTimeout(poll, interval);
      }
    };
    void poll();

    return () => {
      cancelled = true;
      if (timerRef.current !== undefined) window.clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, opts.intervalMs]);

  return view;
}

function errMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
