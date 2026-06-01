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

/**
 * AFF SPR-10 M2 — one prior knowledge unit that THIS investigation reused,
 * READ from a persisted `knowledge.reused` event (SPR-06,
 * `substrate/context_pack/knowledge_reuse.py`). The flywheel's reuse
 * provenance: which prior insight was injected into this investigation's
 * context pack, and where it came from.
 *
 * The payload (generated/types.ts `KnowledgeReusedPayload`) carries NO human
 * label/title for a reused unit — only its `reused_unit_id` and the
 * `source_investigation_id` it came from (parallel arrays). So a `ReusedInsight`
 * carries exactly those two real identifiers, never a fabricated title (rigor
 * #1): the viewer renders the unit id as the link text and routes the link to
 * the prior investigation's existing `/inv/:id` surface (M6 reachability).
 */
export interface ReusedInsight {
  /** The reused prior knowledge unit's id (`reused_unit_ids[i]`). */
  unitId: string;
  /** The prior investigation this unit came from (`source_investigation_ids[i]`);
   *  null when the parallel array didn't carry one for this unit (honest
   *  "unknown origin" — never invented). The viewer links to `/inv/:id` when
   *  present (an EXISTING route — no new route, M6). */
  sourceInvestigationId: string | null;
  /** The real cosine similarity the reuse layer recorded for this unit
   *  (`scores[i]`), or null when the parallel array didn't carry one. Read,
   *  never a floor (mirrors SPR-06's honesty contract). */
  score: number | null;
}

/**
 * AFF SPR-10 M4 — the per-run compounding measurement, the three numbers the
 * spec's headline ("reused N insights · avoided M re-derivations · K fewer
 * sources than cold") reads from. `reused` is REAL today (the count of reused
 * units from `knowledge.reused`). `avoided` and `fewerSources` require a
 * cold-baseline comparison the CLIENT must never compute (rigor #1, out-of-scope
 * §); they come ONLY from a persisted per-run measurement event — which does
 * NOT exist on the substrate yet (SPR-09 built a CROSS-ARM benchmark over a
 * frozen question set, `compounding/benchmark/`, NOT a per-investigation event;
 * there is no `compounding.measured` ActionType). So `avoided`/`fewerSources`
 * parse from such an event IF one is ever emitted, and are null until then —
 * the stat line renders only the numbers it actually has, and renders nothing
 * when there is no measurement at all. See
 * docs/decisions/spr-10-flywheel-surface.md for the honest no-source finding.
 */
export interface CompoundingStat {
  reused: number;
  avoided: number | null;
  fewerSources: number | null;
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
  /** SPR-10 M2 — the prior insights this investigation reused, READ from the
   *  `knowledge.reused` event(s) (SPR-06). An investigation may emit more than
   *  one such event, so this is the UNION of every event's injected units in
   *  encounter order. EMPTY when the run reused nothing (a novel question, or
   *  an all-dropped retrieval) — in which case the viewer renders NOTHING (the
   *  present-only discipline the `qualityScore === null` branch follows). */
  reuseProvenance: ReusedInsight[];
  /** SPR-10 M4 — the per-run compounding measurement; null when no per-run
   *  measurement event was persisted (the common case today — see
   *  `CompoundingStat`). The viewer renders the stat line only from real fields
   *  and shows nothing when this is null. */
  compoundingStat: CompoundingStat | null;
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
  reuseProvenance: [],
  compoundingStat: null,
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

/** SPR-10 M2 — the persisted `knowledge.reused` payload (generated/types.ts
 *  `KnowledgeReusedPayload`). Read structurally with optional fields so a
 *  malformed/partial event degrades to an honest empty rather than throwing.
 *  `reused_unit_ids` / `scores` / `source_investigation_ids` are parallel by
 *  index per SPR-06's contract; we zip them by position and never invent a
 *  missing element. */
interface KnowledgeReusedPayloadShape {
  reused_unit_ids?: string[];
  scores?: number[];
  source_investigation_ids?: string[];
}

/** SPR-10 M4 — a SPECULATIVE per-run compounding measurement payload. NO event
 *  of this shape exists on the substrate today (there is no `compounding.measured`
 *  ActionType — SPR-09's `compounding/benchmark/` is a cross-arm benchmark, not a
 *  per-investigation event). This interface defines the shape we WOULD parse if
 *  such an event were ever emitted, so the render path is provable (a synthetic
 *  fixture drives it in the tests) while the real-data path stays null today.
 *  The client reads `avoided` / `fewer_sources` — it never computes them
 *  (no cold-baseline arithmetic in the client; rigor #1). */
interface CompoundingMeasuredPayloadShape {
  reused?: number;
  avoided?: number;
  fewer_sources?: number;
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
  // SPR-10 M2: the reused prior insights, READ from every knowledge.reused event
  // (an investigation may emit more than one — union them in encounter order).
  const reuseProvenance: ReusedInsight[] = [];
  // SPR-10 M4: the per-run compounding measurement, READ from a persisted
  // per-run measurement event. None exists on the substrate today (see
  // CompoundingMeasuredPayloadShape); seen only when a synthetic/future event
  // is present. Keep the latest in trajectory order.
  let compoundingPayload: CompoundingMeasuredPayloadShape | null = null;

  // SPR-10 M4: the future per-run measurement action type. It is deliberately
  // NOT in the generated `ActionType` union (no such event exists on the
  // substrate today), so we name it as a plain string to compare against
  // `e.action_type` without TypeScript flagging a no-overlap comparison — the
  // honest record that this is a seam for an event the substrate may emit later.
  const COMPOUNDING_MEASURED_ACTION_TYPE: string = "compounding.measured";

  for (const e of events) {
    const at: string = e.action_type;
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
    } else if (at === "knowledge.reused") {
      // SPR-10 M2: zip the parallel arrays by index into one ReusedInsight per
      // INJECTED unit. We invent nothing: a missing parallel element (a shorter
      // scores / source_investigation_ids array) becomes null, never a guess.
      const kr = p as KnowledgeReusedPayloadShape | undefined;
      const unitIds = kr?.reused_unit_ids ?? [];
      const scores = kr?.scores ?? [];
      const sources = kr?.source_investigation_ids ?? [];
      unitIds.forEach((unitId, i) => {
        reuseProvenance.push({
          unitId,
          sourceInvestigationId:
            typeof sources[i] === "string" ? sources[i] : null,
          score: typeof scores[i] === "number" ? scores[i] : null,
        });
      });
    } else if (at === COMPOUNDING_MEASURED_ACTION_TYPE) {
      // SPR-10 M4: NO event of this action_type exists on the substrate today
      // (it is not in generated/types.ts ActionType). This branch is the future
      // seam: if a per-run measurement event is ever emitted under this name, we
      // READ its three fields; we never compute avoided/fewer-than-cold here.
      // A synthetic fixture exercises this branch in the tests (non-vacuity);
      // the empty/real-data path leaves compoundingPayload null.
      compoundingPayload = p as CompoundingMeasuredPayloadShape;
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

  // SPR-10 M2: attach the reused prior insights (empty when nothing was reused —
  // the viewer then renders nothing, the present-only discipline).
  result.reuseProvenance = reuseProvenance;

  // SPR-10 M4: attach the per-run compounding stat — READ from a per-run
  // MEASUREMENT event ONLY. Per M4's acceptance criteria the field is "null when
  // no measurement" and "with the measurement absent the stat line is not in the
  // DOM". The reused COUNT is already surfaced by M3's reuseProvenance list, so we
  // do NOT synthesize a compoundingStat from the knowledge.reused count — a stat
  // line without a measurement would imply one happened (rigor #1). No
  // `compounding.measured` event exists on the substrate today (see
  // CompoundingMeasuredPayloadShape), so this stays null in practice; the synthetic
  // fixture in the tests proves the render path for when one is ever emitted.
  if (compoundingPayload) {
    result.compoundingStat = {
      reused:
        typeof compoundingPayload.reused === "number"
          ? compoundingPayload.reused
          : reuseProvenance.length,
      avoided:
        typeof compoundingPayload.avoided === "number"
          ? compoundingPayload.avoided
          : null,
      fewerSources:
        typeof compoundingPayload.fewer_sources === "number"
          ? compoundingPayload.fewer_sources
          : null,
    };
  }

  return result;
}
