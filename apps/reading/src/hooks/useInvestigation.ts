import { useEffect, useMemo, useState } from "react";

import type { Event } from "../generated/types";
import { getInvestigationStatus, getTrajectory } from "../lib/api";
import type { InvestigationStatus } from "../lib/api";
import { useEventStream } from "./useEventStream";

export interface InvestigationState {
  id: string;
  status: "loading" | "in_progress" | "completed" | "failed" | "not_found";
  question: string | null;
  events: Event[];
  terminalPayload: Record<string, unknown> | null;
  costTotal: number;
  /** Latest investigation.completed | .failed event timestamp, if any. */
  completedAt: string | null;
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
 * when the trajectory is empty (no investigation by that id);
 * ``"in_progress" | "completed" | "failed"`` based on terminal events.
 */
export function useInvestigation(
  investigationId: string | null,
): InvestigationState {
  const [seedEvents, setSeedEvents] = useState<Event[]>([]);
  const [status, setStatus] = useState<InvestigationStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const { events: liveEvents } = useEventStream(investigationId);

  // Initial trajectory + status fetch on id change.
  useEffect(() => {
    if (!investigationId) {
      setSeedEvents([]);
      setStatus(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const [traj, st] = await Promise.all([
          getTrajectory(investigationId),
          getInvestigationStatus(investigationId).catch((): InvestigationStatus | null => null),
        ]);
        if (cancelled) return;
        setSeedEvents(traj.events ?? []);
        setStatus(st);
      } catch {
        // 404 or similar — leave seedEvents empty, status null → "not_found"
        if (cancelled) return;
        setSeedEvents([]);
        setStatus(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [investigationId]);

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
    Pick<InvestigationState, "status" | "question" | "terminalPayload" | "costTotal" | "completedAt">
  >(() => {
    if (loading) {
      return {
        status: "loading",
        question: null,
        terminalPayload: null,
        costTotal: 0,
        completedAt: null,
      };
    }
    if (events.length === 0) {
      return {
        status: "not_found",
        question: null,
        terminalPayload: null,
        costTotal: 0,
        completedAt: null,
      };
    }
    let question: string | null = null;
    let terminal: { type: string; row: Event } | null = null;
    let cost = 0;
    for (const e of events) {
      const at = e.action_type;
      if (at === "investigation.start_requested" && question === null) {
        const p = e.payload as { question?: string } | undefined;
        if (p?.question) question = p.question;
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
    };
  }, [events, loading, status]);

  return {
    id: investigationId ?? "",
    events,
    ...derived,
  };
}
