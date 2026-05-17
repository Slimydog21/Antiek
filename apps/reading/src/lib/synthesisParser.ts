import type { Event } from "../generated/types";

/**
 * Hybrid-rendering parser: takes the trajectory + terminal payload of a
 * completed investigation and produces a ``ParsedSynthesis`` shape
 * suitable for the MasterMdViewer.
 *
 * The substrate emits structured ``synthesize.delivered`` carrying the
 * full thesis JSON (thesis components, falsification conditions,
 * execution risks, recommendation). We parse that structure here so
 * the renderer can wrap each claim text in a ``<span data-claim-id>``
 * for hover-citation interactivity while still flowing the prose
 * naturally.
 *
 * The investigation.completed event carries a compact summary; the
 * synthesize.delivered event carries the full structure. We prefer the
 * latter.
 */

export type Confidence = "high" | "moderate" | "low" | "unknown";

export type Recommendation =
  | "proceed"
  | "pass"
  | "conditional"
  | "undetermined"
  | "insufficient_evidence";

export interface ParsedClaim {
  index: number; // 1-based component number
  claim: string;
  rationale?: string;
  confidence: Confidence;
  effectiveSourceTier: number | null;
  hedgingRequired: boolean;
  chunkIds: string[];
  supportingPathIndices: number[];
}

export interface ParsedFalsification {
  condition: string;
  specificObservable?: string;
}

export interface ParsedExecutionRisk {
  risk: string;
  mitigation?: string;
}

export interface ParsedSynthesis {
  thesisSummary: string;
  components: ParsedClaim[];
  falsificationConditions: ParsedFalsification[];
  executionRisks: ParsedExecutionRisk[];
  recommendation: Recommendation;
  hardConstraintsSatisfied: boolean | null;
  totalCostUsd: number;
  question: string | null;
  masterMdPath: string | null;
  domainsPatched: string[];
  /** Map every chunk_id we encounter → set of component indices that cite it.
   *  Used by the hover modal to navigate citations bidirectionally. */
  chunkCitations: Record<string, number[]>;
}

const EMPTY_SYNTHESIS: ParsedSynthesis = {
  thesisSummary: "",
  components: [],
  falsificationConditions: [],
  executionRisks: [],
  recommendation: "undetermined",
  hardConstraintsSatisfied: null,
  totalCostUsd: 0,
  question: null,
  masterMdPath: null,
  domainsPatched: [],
  chunkCitations: {},
};

interface SynthesizeDeliveredPayload {
  thesis_summary?: string;
  thesis_components?: Array<{
    claim?: string;
    rationale?: string;
    confidence?: Confidence;
    effective_source_tier?: number | null;
    hedging_required?: boolean;
    supporting_chunk_ids?: string[];
    supporting_path_indices?: number[];
  }>;
  falsification_conditions?: Array<{
    condition?: string;
    specific_observable?: string;
  }>;
  execution_risks?: Array<{ risk?: string; mitigation?: string }>;
  implicit_recommendation?: Recommendation;
  constraint_compliance?: {
    hard_constraints_satisfied?: boolean;
  };
}

interface CompletedPayload {
  thesis_summary?: string;
  implicit_recommendation?: Recommendation;
  master_md_path?: string | null;
  domains_patched?: string[];
}

/**
 * Walk events to extract the canonical synthesis structure + sum costs.
 * Returns `null` when the investigation has no synthesize.delivered yet
 * (still in progress) — callers should fall back to TrajectoryView.
 */
export function parseSynthesis(events: Event[]): ParsedSynthesis | null {
  let synthDelivered: SynthesizeDeliveredPayload | null = null;
  let completed: CompletedPayload | null = null;
  let question: string | null = null;
  let totalCost = 0;

  for (const e of events) {
    const at = e.action_type;
    const p = e.payload as unknown as Record<string, unknown> | undefined;
    if (at === "synthesize.delivered") {
      synthDelivered = p as SynthesizeDeliveredPayload;
    } else if (at === "investigation.completed") {
      completed = p as CompletedPayload;
    } else if (at === "investigation.start_requested") {
      const q = (p as { question?: string } | undefined)?.question;
      if (q) question = q;
    } else if (at === "dispatch.call") {
      const c = (p as { cost_usd?: number } | undefined)?.cost_usd;
      if (typeof c === "number") totalCost += c;
    }
  }

  if (!synthDelivered && !completed) return null;

  const result: ParsedSynthesis = {
    ...EMPTY_SYNTHESIS,
    question,
    totalCostUsd: totalCost,
    masterMdPath: completed?.master_md_path ?? null,
    domainsPatched: completed?.domains_patched ?? [],
    recommendation:
      synthDelivered?.implicit_recommendation ??
      completed?.implicit_recommendation ??
      "undetermined",
    thesisSummary:
      synthDelivered?.thesis_summary ??
      completed?.thesis_summary ??
      "",
  };

  if (synthDelivered?.thesis_components) {
    result.components = synthDelivered.thesis_components.map((c, i) => ({
      index: i + 1,
      claim: c.claim ?? "",
      rationale: c.rationale,
      confidence: c.confidence ?? "unknown",
      effectiveSourceTier: c.effective_source_tier ?? null,
      hedgingRequired: c.hedging_required ?? false,
      chunkIds: c.supporting_chunk_ids ?? [],
      supportingPathIndices: c.supporting_path_indices ?? [],
    }));
    for (const c of result.components) {
      for (const cid of c.chunkIds) {
        if (!result.chunkCitations[cid]) result.chunkCitations[cid] = [];
        result.chunkCitations[cid].push(c.index);
      }
    }
  }

  if (synthDelivered?.falsification_conditions) {
    result.falsificationConditions = synthDelivered.falsification_conditions.map(
      (f) => ({
        condition: f.condition ?? "",
        specificObservable: f.specific_observable,
      }),
    );
  }

  if (synthDelivered?.execution_risks) {
    result.executionRisks = synthDelivered.execution_risks.map((r) => ({
      risk: r.risk ?? "",
      mitigation: r.mitigation,
    }));
  }

  if (synthDelivered?.constraint_compliance) {
    result.hardConstraintsSatisfied =
      synthDelivered.constraint_compliance.hard_constraints_satisfied ?? null;
  }

  return result;
}
