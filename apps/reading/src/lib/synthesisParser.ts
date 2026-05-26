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

/**
 * A named source backing a claim, resolved through the provenance chain
 * claim → chunk → document → (title, locator). SPR-04 renders THIS, not a
 * raw chunk id / `[N chunks]` count: a reader thinks in sources, not in the
 * engine's retrieval unit. One source groups all of a claim's chunks that
 * land in the same document (so "3 chunks of one paper" reads as one named
 * source, not "[3 chunks]").
 *
 * The resolution is async (it needs the chunk→document join the `getChunk`
 * endpoint owns), so the PARSER only groups the chunk ids per claim; the
 * VIEWER resolves titles + servability. This shape is the contract between
 * them.
 */
export interface ClaimSourceGroup {
  /** A representative chunk id used to resolve the document (any chunk of
   *  the group resolves the same document title + servability). */
  resolveChunkId: string;
  /** Every chunk id this claim cites in the same (still-unresolved)
   *  document bucket. Bucketing by document is the viewer's job after it
   *  resolves document_id; before resolution we only know chunk ids, so a
   *  claim starts with one group per chunk and the viewer coalesces. */
  chunkIds: string[];
}

/**
 * SPR-11 M3 — the §14.4 inline-rubric verdict for this answer, READ from the
 * `rubric.scored` event the orchestrator emits after Phase 6. The parser only
 * reads the persisted event; it never recomputes the score (the scorer's
 * algorithm is substrate-owned and untouched here). `composite` is the
 * headline in [0, 1]; the four sub-scores are present only when the persisted
 * note encoded them and are null otherwise (honest, never invented).
 */
export interface QualityScore {
  composite: number;
  voiceStyle: number | null;
  conviction: number | null;
  citationDensity: number | null;
  constraintCompliance: number | null;
  notes: string;
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
  /** The inline-rubric verdict for this answer; null when no `rubric.scored`
   *  event was persisted (the no-synthesis / no-key case). The viewer renders
   *  a quiet quality cue from this and shows nothing when it's null. */
  qualityScore: QualityScore | null;
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
  qualityScore: null,
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

/** The persisted `rubric.scored` payload. `final_score` is the composite; the
 *  four sub-scores ride along inside `notes` as
 *  `voice=… conviction=… citation_density=… constraint=…` (the orchestrator
 *  writes them there), so we read them back when present. */
interface RubricScoredPayload {
  final_score?: number;
  notes?: string;
}

/** Pull one named sub-score out of the rubric note, or null when absent /
 *  out of range. Mirrors the backend reader so the two surfaces agree. */
function subScoreFromNotes(notes: string, key: string): number | null {
  const m = notes.match(new RegExp(`\\b${key}=([01](?:\\.\\d+)?)`));
  if (!m) return null;
  const v = Number(m[1]);
  return Number.isFinite(v) && v >= 0 && v <= 1 ? v : null;
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
  // SPR-11 M3: the inline-rubric verdict, READ from the last rubric.scored
  // event (never recomputed). Keep the latest in trajectory order.
  let rubricPayload: RubricScoredPayload | null = null;

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
    } else if (at === "rubric.scored") {
      rubricPayload = p as RubricScoredPayload;
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

  // SPR-11 M3: attach the persisted inline-rubric verdict when one exists.
  // A rubric.scored event must carry a numeric final_score; without it we
  // leave qualityScore null rather than guess a value (rigor #1).
  if (rubricPayload && typeof rubricPayload.final_score === "number") {
    const notes = typeof rubricPayload.notes === "string" ? rubricPayload.notes : "";
    result.qualityScore = {
      composite: Math.max(0, Math.min(1, rubricPayload.final_score)),
      voiceStyle: subScoreFromNotes(notes, "voice"),
      conviction: subScoreFromNotes(notes, "conviction"),
      citationDensity: subScoreFromNotes(notes, "citation_density"),
      constraintCompliance: subScoreFromNotes(notes, "constraint"),
      notes,
    };
  }

  return result;
}
