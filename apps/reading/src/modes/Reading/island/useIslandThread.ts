/**
 * useIslandThread — one island's live thread projection (island SPR-01).
 *
 * Composes the EXISTING projections, adds zero stores and zero new fetches
 * beyond what they already make:
 *
 *   - useInvestigation(investigationId) — the CANONICAL status: the event
 *     projection (trajectory seed + WebSocket live tail + status fetch —
 *     NOT polling; useInvestigation.ts:43) with cost advancing reactively as
 *     dispatch.call events land.
 *   - useInvestigationList + useInvestigationTree — the thread FAMILY (the
 *     root and its chases as one tree, substrate parent ids winning over the
 *     localStorage fallback), and the summary's stopped/failed refinement.
 *   - getSession(investigationId) — the session-level ResearchRunState,
 *     refined only when resolvable. There is no session-for-investigation
 *     lookup route today, so "resolvable" means the thread is itself a
 *     session container; any non-OK answer is an honest unresolvable (the
 *     projection alone decides), never a fabricated session.
 *   - getDistillation(investigationId), fetched only once the thread is
 *     terminal — the insight count behind complete vs complete_empty.
 *
 * Status is the pure, total islandStatus mapping (islandModel.ts).
 */
import { useEffect, useMemo, useState } from "react";

import { getSession } from "../../../api/research";
import type { ResearchRunState } from "../../../api/research";
import { useInvestigation } from "../../../hooks/useInvestigation";
import { useInvestigationList } from "../../../hooks/useInvestigationList";
import { useInvestigationTree } from "../../../hooks/useInvestigationTree";
import { getDistillation } from "../../../lib/api";
import type { DistilledNode, InvestigationSummary } from "../../../lib/api";
import {
  islandStatus,
  selectIslandFamily,
  type IslandFamilyNode,
  type IslandStatus,
} from "./islandModel";

export interface IslandOutcome {
  insights: DistilledNode[];
  questions: DistilledNode[];
}

export interface IslandThreadState {
  status: IslandStatus;
  /** The event projection's live cost (advances while the thread runs). */
  costTotal: number;
  /** The thread's question, when the projection knows it. */
  question: string | null;
  /** The island's thread family (root + chases, pre-order). */
  family: IslandFamilyNode[];
  /** True while the FIRST projection load is in flight. */
  loading: boolean;
  /** True while the terminal thread's distill read is in flight. */
  outcomeLoading: boolean;
  /** The distilled outcome (lead insights + open questions), present once the
   *  terminal thread's distill read lands — null before or on failure. */
  outcome: IslandOutcome | null;
  /** How the status was reached, for an honest debug view. */
  sessionState: ResearchRunState | null;
  /** Refetch the investigations list (the family's source) — called after a
   *  dig-deeper launch so the new chase appears in the family view
   *  immediately, without a reload. */
  refetchFamily: () => void;
}

export function useIslandThread(investigationId: string | null): IslandThreadState {
  const projection = useInvestigation(investigationId);
  const { investigations, refetch: refetchFamily } = useInvestigationList();
  const tree = useInvestigationTree(investigations);

  const summary: InvestigationSummary | null = useMemo(
    () =>
      investigationId
        ? (investigations.find((i) => i.investigation_id === investigationId) ?? null)
        : null,
    [investigations, investigationId],
  );

  const family = useMemo(
    () => (investigationId ? selectIslandFamily(tree, investigationId) : []),
    [tree, investigationId],
  );

  // The session facet, only when resolvable (the thread is itself a session
  // container). Any non-OK answer is an honest unresolvable.
  const [sessionState, setSessionState] = useState<ResearchRunState | null>(null);
  useEffect(() => {
    if (!investigationId) {
      setSessionState(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const session = await getSession(investigationId);
        if (cancelled) return;
        const mine = session.researches.find(
          (r) => r.investigation_id === investigationId,
        );
        setSessionState(mine?.state ?? null);
      } catch {
        if (!cancelled) setSessionState(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [investigationId]);

  // The insight count behind complete vs complete_empty — fetched only once
  // the thread is terminal (never a per-render fetch).
  const projectionTerminal =
    projection.status === "completed" ||
    projection.status === "failed" ||
    summary?.status === "completed" ||
    summary?.status === "failed" ||
    summary?.status === "stopped";
  const [insightCount, setInsightCount] = useState<number | null>(null);
  const [outcome, setOutcome] = useState<IslandOutcome | null>(null);
  const [outcomeLoading, setOutcomeLoading] = useState(false);
  useEffect(() => {
    if (!investigationId || !projectionTerminal) {
      setInsightCount(null);
      setOutcome(null);
      return;
    }
    let cancelled = false;
    setOutcomeLoading(true);
    void (async () => {
      try {
        const distillation = await getDistillation(investigationId);
        if (cancelled) return;
        setInsightCount(distillation.insights.length);
        setOutcome({
          insights: distillation.insights,
          questions: distillation.questions,
        });
      } catch {
        // A terminal thread whose distill read fails still gets an honest
        // status — unknown insight count, never a fabricated empty.
        if (!cancelled) {
          setInsightCount(null);
          setOutcome(null);
        }
      } finally {
        if (!cancelled) setOutcomeLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [investigationId, projectionTerminal]);

  const status = islandStatus({
    projection: investigationId ? projection.status : null,
    summary: summary?.status ?? null,
    session: sessionState,
    insightCount,
  });

  return {
    status,
    costTotal: projection.costTotal,
    question: projection.question ?? summary?.question ?? null,
    family,
    loading: projection.status === "loading",
    outcomeLoading,
    outcome,
    sessionState,
    refetchFamily,
  };
}
