/**
 * DRW SPR-09 M4 — live session consumption + reconnect.
 *
 * Polls SPR-06's durable `GET /research/sessions/{id}` (status + cost) on an
 * interval, stopping once every research is terminal. Polling — not an
 * EventSource — is the deliberate choice: it matches the codebase's dominant
 * live-update idiom (setInterval + cancellation), and because each poll
 * re-derives authoritative state from the durable endpoint (which itself
 * falls back to `reconstruct_session` from the event log), "reconnect and
 * resume" is free and gap-free — a dropped poll or a server restart simply
 * resolves on the next tick. The richer per-step SSE stream
 * (`sessionStreamUrl`) is a future EventSource upgrade; the monitor does not
 * depend on it. Snapshots are whole-state (not appended deltas), so there is
 * nothing to dedup.
 *
 * Failures (FFX SPR-04, A-14): a session the backend says does not exist
 * (describeFailure kind "not_found") is terminal: `missing` is set and the
 * loop stops after that one request, because re-polling a 404 cannot make the
 * session appear. Any other failure keeps the reconnect behaviour, backing off
 * (interval, 2x, 4x … capped) across consecutive failures, and `error` carries
 * describeFailure's plain title, never the raw request line.
 */

import { useEffect, useRef, useState } from "react";

import {
  getSession,
  TERMINAL_STATES,
  type ResearchStatus,
  type HardCeilingSnapshot,
  type SessionCost,
} from "../../api/research";
import type { ResearchSourcePolicy } from "../../lib/api";
import { describeFailure } from "../../shared/failure";

export interface SessionView {
  researches: ResearchStatus[];
  cost: SessionCost | null;
  hardCeiling: HardCeilingSnapshot | null;
  live: boolean;
  allTerminal: boolean;
  loading: boolean;
  sourcePolicy: ResearchSourcePolicy[];
  sourcePolicyExecution: "metadata_only" | "runner_consumed" | null;
  /** Plain-language title of the last poll failure; never a status or path. */
  error: string | null;
  /** The backend reported the session does not exist; polling has stopped. */
  missing: boolean;
}

/** Longest wait between reconnect attempts after consecutive failures. */
const MAX_BACKOFF_MS = 30_000;

const EMPTY: SessionView = {
  researches: [],
  cost: null,
  hardCeiling: null,
  live: false,
  allTerminal: false,
  loading: true,
  sourcePolicy: [],
  sourcePolicyExecution: null,
  error: null,
  missing: false,
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
    let consecutiveFailures = 0;
    setView({ ...EMPTY, loading: true });

    const poll = async () => {
      try {
        const s = await getSession(sessionId);
        if (cancelled) return;
        consecutiveFailures = 0;
        const allTerminal =
          (s.all_terminal ?? s.researches.every((r) => TERMINAL_STATES.has(r.state))) &&
          s.researches.length > 0;
        setView({
          researches: s.researches,
          cost: s.cost ?? null,
          hardCeiling: s.hard_ceiling ?? null,
          live: s.live,
          allTerminal,
          loading: false,
          sourcePolicy: s.source_policy ?? [],
          sourcePolicyExecution: s.source_policy_execution ?? null,
          error: null,
          missing: false,
        });
        // Keep polling until every research is terminal; then stop (the
        // monitor shows the final state, no wasted requests).
        const evidenceFinal =
          !s.hard_ceiling ||
          (s.hard_ceiling.run_state === "closed_reconciled" &&
            s.hard_ceiling.unknown_outcome_count === 0);
        if (!allTerminal) {
          terminalEvidencePolls = 0;
          timerRef.current = window.setTimeout(poll, interval);
        } else if (!evidenceFinal && terminalEvidencePolls < 3) {
          terminalEvidencePolls += 1;
          timerRef.current = window.setTimeout(
            poll,
            interval * 2 ** (terminalEvidencePolls - 1),
          );
        }
      } catch (e) {
        if (cancelled) return;
        const failure = describeFailure(e, { what: "reach this research session" });
        if (failure.kind === "not_found") {
          // Terminal: no timer is scheduled, so this was the last request.
          setView((v) => ({ ...v, loading: false, error: failure.title, missing: true }));
          return;
        }
        // Transient failure → surface it but keep retrying (reconnect), with backoff.
        consecutiveFailures += 1;
        setView((v) => ({ ...v, loading: false, error: failure.title, missing: false }));
        timerRef.current = window.setTimeout(
          poll,
          Math.min(MAX_BACKOFF_MS, interval * 2 ** (consecutiveFailures - 1)),
        );
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
