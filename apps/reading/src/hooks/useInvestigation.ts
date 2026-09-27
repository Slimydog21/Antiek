import { useCallback, useEffect, useMemo, useState } from "react";

import type { Event } from "../generated/types";
import {
  ApiError,
  classifyClientError,
  getInvestigationStatus,
  getTrajectory,
} from "../lib/api";
import type {
  ClientFailureClassification,
  InvestigationStatus,
  ResearchSourcePolicy,
} from "../lib/api";
import { useEventStream } from "./useEventStream";

export interface InvestigationState {
  id: string;
  /** ``"error"`` = the seed fetch failed (outage, auth, network), so whether
   *  the research exists is UNKNOWN — never shown as ``"not_found"``. */
  status: "loading" | "in_progress" | "completed" | "failed" | "not_found" | "error";
  question: string | null;
  events: Event[];
  terminalPayload: Record<string, unknown> | null;
  costTotal: number;
  /** Latest investigation.completed | .failed event timestamp, if any. */
  completedAt: string | null;
  /** The live WebSocket's connection state, surfaced so a live view can show
   *  a reconnecting beat instead of a frozen feed (SPR-02 M2). Distinct from
   *  `status`: a research can be `in_progress` while the socket is briefly
   *  `closed`/`connecting` between reconnect attempts. */
  streamStatus: "connecting" | "open" | "closed" | "error";
  /** How many times the live socket has reconnected (from useEventStream).
   *  A live view can show "reconnecting…" when this advances mid-run. */
  reconnects: number;
  /** Metadata-only source-pack intent recorded when this research started. */
  sourcePolicy: ResearchSourcePolicy[];
  /** Why the seed fetch failed when ``status === "error"``; null otherwise.
   *  Optional so hand-built fixtures need not carry it. */
  loadError?: ClientFailureClassification | null;
  /** Re-run the seed fetch (the retry for ``status === "error"``). */
  retry?: () => void;
}

/**
 * Subscribe to one investigation's full state.
 *
 * On id change:
 *   1. Fetch /trajectory/{id} for the seed history
 *   2. Subscribe to /ws/events?investigation_id={id} for the live tail
 *   3. Fetch /investigations/{id} for the terminal payload (if terminal)
 *
 * Recomputes `costTotal` reactively as new dispatch.call events arrive.
 *
 * Returns ``status: "loading"`` during the initial fetch; ``"not_found"``
 * when the trajectory is empty (no investigation by that id); ``"error"``
 * when the seed fetch failed and existence is unknown (``retry`` re-runs it);
 * ``"in_progress" | "completed" | "failed"`` based on terminal events.
 */
export function useInvestigation(
  investigationId: string | null,
): InvestigationState {
  const [seedEvents, setSeedEvents] = useState<Event[]>([]);
  const [status, setStatus] = useState<InvestigationStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<ClientFailureClassification | null>(null);
  const [attempt, setAttempt] = useState<number>(0);
  const {
    events: liveEvents,
    status: streamStatus,
    reconnects,
  } = useEventStream(investigationId);

  // Initial trajectory + status fetch on id change.
  useEffect(() => {
    if (!investigationId) {
      setSeedEvents([]);
      setStatus(null);
      setLoadError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    void (async () => {
      try {
        const [traj, st] = await Promise.all([
          getTrajectory(investigationId),
          getInvestigationStatus(investigationId).catch((): InvestigationStatus | null => null),
        ]);
        if (cancelled) return;
        setSeedEvents(traj.events ?? []);
        setStatus(st);
      } catch (e) {
        if (cancelled) return;
        setSeedEvents([]);
        setStatus(null);
        // GET /trajectory answers an unknown id with 200 + zero events, so
        // only an explicit 404 means "no such research". Anything else (5xx,
        // 401/403, a dropped connection) leaves existence unknown: surface it
        // as a retryable error, never as a definite "not_found".
        if (!(e instanceof ApiError && e.status === 404)) {
          setLoadError(classifyClientError(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [investigationId, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  // Merge seed + live events, dedup by event_id (live events overlap
  // with the seed fetch for events emitted during the fetch window).
  const events = useMemo(() => {
    const seen = new Set<string>();
    const merged: Event[] = [];
    for (const e of [...seedEvents, ...liveEvents]) {
      const eid = e.event_id;
      if (!eid || seen.has(eid)) continue;
      seen.add(eid);
      merged.push(e);
    }
    // Order by emitted_at ascending (ISO8601 strings sort lex-compatible).
    merged.sort((a, b) =>
      (a.emitted_at ?? "").localeCompare(b.emitted_at ?? ""),
    );
    return merged;
  }, [seedEvents, liveEvents]);

  // Recompute derived fields whenever events change.
  const derived = useMemo<
    Pick<
      InvestigationState,
      "status" | "question" | "terminalPayload" | "costTotal" | "completedAt" | "sourcePolicy"
    >
  >(() => {
    if (loading) {
      return {
        status: "loading",
        question: null,
        terminalPayload: null,
        costTotal: 0,
        completedAt: null,
        sourcePolicy: [],
      };
    }
    if (loadError !== null && events.length === 0) {
      return {
        status: "error",
        question: null,
        terminalPayload: null,
        costTotal: 0,
        completedAt: null,
        sourcePolicy: [],
      };
    }
    if (events.length === 0) {
      return {
        status: "not_found",
        question: null,
        terminalPayload: null,
        costTotal: 0,
        completedAt: null,
        sourcePolicy: status?.source_policy ?? [],
      };
    }
    let question: string | null = null;
    let sourcePolicy: ResearchSourcePolicy[] = status?.source_policy ?? [];
    let terminal: { type: string; row: Event } | null = null;
    let cost = 0;
    for (const e of events) {
      const at = e.action_type;
      if (at === "investigation.start_requested" && question === null) {
        const p = e.payload as {
          question?: string;
          source_policy?: ResearchSourcePolicy[];
        } | undefined;
        if (p?.question) question = p.question;
        if (Array.isArray(p?.source_policy)) sourcePolicy = p.source_policy;
      } else if (
        at === "investigation.completed" ||
        at === "investigation.failed"
      ) {
        terminal = { type: at, row: e };
      } else if (at === "dispatch.call") {
        const p = e.payload as { cost_usd?: number } | undefined;
        if (typeof p?.cost_usd === "number") cost += p.cost_usd;
      }
    }
    return {
      status:
        terminal === null
          ? "in_progress"
          : terminal.type === "investigation.completed"
            ? "completed"
            : "failed",
      question,
      terminalPayload:
        (terminal?.row.payload as Record<string, unknown> | undefined) ??
        (status?.terminal_payload ?? null),
      costTotal: cost,
      completedAt: terminal?.row.emitted_at ?? null,
      sourcePolicy,
    };
  }, [events, loading, status, loadError]);

  return {
    id: investigationId ?? "",
    events,
    streamStatus,
    reconnects,
    loadError,
    retry,
    ...derived,
  };
}
