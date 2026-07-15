import { useCallback, useMemo, useState } from "react";

import { startInvestigation } from "../lib/api";
import type { ResearchRouteCandidate, ResearchTier } from "../lib/api";
import type { Event } from "../generated/types";
import { useEventStream } from "./useEventStream";

/**
 * useStartInvestigation — the single sanctioned path for starting a NEW
 * investigation from the Research home, and for letting the AI be *felt*
 * the moment it starts.
 *
 * Why a hook (not inline in ChatInputArea / EmptyState): the start flow
 * has two concerns that the spec wants kept honest and un-duplicated:
 *
 *   1. The POST.   `startInvestigation` is the only place the API call
 *      lives — this hook calls it; nothing reimplements it.
 *   2. The wait.   Between "id returned" and "the route's
 *      InvestigationCenter has loaded the trajectory", the user must NOT
 *      see a silent `…`. So the instant the id comes back we attach the
 *      REAL `useEventStream(id)` and surface its genuine
 *      connecting → streaming state plus the live event count and the
 *      accumulated dispatch cost. No mock animation stands in for
 *      progress — `phase` is `startedId == null ? "idle" : stream.status`.
 *
 * The caller decides what to do once activity begins (navigate to
 * `/inv/:id`); this hook just owns submit + the honest in-between state.
 */

export type StartPhase =
  | "idle" // nothing submitted yet
  | "posting" // POST /investigations in flight
  | "connecting" // id back, WS opening
  | "streaming" // WS open, real events arriving (or open + awaiting first)
  | "failed" // id was returned, but the run hit a terminal investigation.failed
  | "error"; // POST failed

export interface StartInvestigationState {
  /** The new investigation id once the POST returns, else null. */
  startedId: string | null;
  /** Honest lifecycle phase — drives the "thinking…/working…" surface. */
  phase: StartPhase;
  /** Real events streamed since the id returned (the live tail). */
  events: Event[];
  /** Accumulated cost from streamed dispatch.call events (USD). */
  liveCost: number;
  /**
   * True once a terminal ``investigation.failed`` event has streamed for
   * the started id — the run aborted before producing a result (e.g. the
   * model provider isn't configured), so navigating to /inv/:id would
   * strand the operator on an empty surface.
   */
  failed: boolean;
  /**
   * Human-readable reason from the ``investigation.failed`` event's
   * ``reason`` payload, when present; null otherwise. Surfaced verbatim
   * is not ideal (it's a diagnostic), so the caller frames it; this is the
   * raw signal.
   */
  failureReason: string | null;
  /** POST/validation error message, if any. */
  error: string | null;
  /** True from submit() entry until the POST resolves or rejects. */
  busy: boolean;
  /**
   * Submit a question. Validates (>= 3 chars), POSTs, and on success
   * stores the id (which attaches the live stream). Returns the new id,
   * or null on validation/POST failure. Never throws.
   */
  submit: (input: {
    question: string;
    parentInvestigationId?: string;
    spawnContext?: string;
    /** SPR-01 M3: curated fast/deep tier from the research entry. */
    researchTier?: ResearchTier;
    route?: {
      candidate: ResearchRouteCandidate;
      promptFingerprint: string;
      policyVersion: string;
    };
  }) => Promise<string | null>;
  /** Reset back to idle (e.g. after the caller has navigated away). */
  reset: () => void;
}

export function useStartInvestigation(): StartInvestigationState {
  const [startedId, setStartedId] = useState<string | null>(null);
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The REAL stream. Null until the id returns → no socket, status "closed".
  const stream = useEventStream(startedId);

  const liveCost = useMemo(() => {
    let cost = 0;
    for (const e of stream.events) {
      if (e.action_type === "dispatch.call") {
        const p = e.payload as { cost_usd?: number } | undefined;
        if (typeof p?.cost_usd === "number") cost += p.cost_usd;
      }
    }
    return cost;
  }, [stream.events]);

  // Terminal failure detection from the REAL stream. The substrate emits an
  // ``investigation.failed`` event (Loop 1 aborted before completion) whose
  // ``reason`` payload carries the diagnostic. This is exactly what fires in
  // production when no model provider is configured: an id is returned, then
  // phase 1 aborts immediately. We mirror the liveCost narrowing pattern —
  // gate on the top-level action_type, then read the typed payload.
  const failureReason = useMemo<string | null>(() => {
    for (const e of stream.events) {
      if (e.action_type === "investigation.failed") {
        const p = e.payload as { reason?: unknown } | undefined;
        return typeof p?.reason === "string" && p.reason.trim().length > 0
          ? p.reason
          : "";
      }
    }
    return null;
  }, [stream.events]);
  const failed = failureReason !== null;

  const phase: StartPhase = useMemo(() => {
    if (error) return "error";
    if (posting) return "posting";
    if (!startedId) return "idle";
    // A terminal investigation.failed event outranks the socket state: the
    // run aborted, so we surface that honestly rather than a "working" lie.
    if (failed) return "failed";
    // id is back — reflect the genuine socket state. "open" with real
    // frames is streaming; "open" awaiting the first frame is still the
    // honest working state, so we treat open as streaming and let the
    // event count tell the finer story. connecting / closed / error from
    // the socket map to "connecting" (the reconnect backoff lives in the
    // stream hook).
    return stream.status === "open" ? "streaming" : "connecting";
  }, [error, posting, startedId, failed, stream.status]);

  const submit = useCallback(
    async (input: {
      question: string;
      parentInvestigationId?: string;
      spawnContext?: string;
      researchTier?: ResearchTier;
      route?: {
        candidate: ResearchRouteCandidate;
        promptFingerprint: string;
        policyVersion: string;
      };
    }): Promise<string | null> => {
      const q = input.question.trim();
      if (!q || q.length < 3) {
        setError("Question is too short. At least 3 characters.");
        return null;
      }
      setPosting(true);
      setError(null);
      try {
        const route = input.route;
        const resp = await startInvestigation({
          question: q,
          parent_investigation_id: input.parentInvestigationId,
          spawn_context: input.spawnContext,
          // Omitted when undefined → server defaults to "deep".
          // Exactly one launch authority input. Preview failure deliberately
          // falls back to the legacy tier contract instead of blocking launch.
          research_tier: route ? undefined : input.researchTier,
          route_choice_id: route?.candidate.choice_id,
          route_prompt_fingerprint: route?.promptFingerprint,
          route_policy_version: route?.policyVersion,
          route_configuration_fingerprint: route?.candidate.configuration_fingerprint,
        });
        setStartedId(resp.investigation_id);
        return resp.investigation_id;
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(`Submit failed: ${msg}`);
        return null;
      } finally {
        setPosting(false);
      }
    },
    [],
  );

  const reset = useCallback(() => {
    setStartedId(null);
    setPosting(false);
    setError(null);
  }, []);

  return {
    startedId,
    phase,
    events: stream.events,
    liveCost,
    failed,
    failureReason,
    error,
    busy: posting,
    submit,
    reset,
  };
}
