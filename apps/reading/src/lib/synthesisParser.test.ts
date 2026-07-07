/**
 * synthesisParser.test.ts — the structure the named-source render (SPR-04
 * M1) reads from. The parser stays structural: it groups a claim's chunk
 * ids so the viewer can resolve them into named sources. It must NOT emit
 * any "[N chunks]" count — the count is the engine's unit, not the
 * reader's; the viewer turns chunks into named sources.
 */
import { describe, expect, it } from "vitest";

import { parseSynthesis } from "./synthesisParser";
import type { Event } from "../generated/types";

function ev(action_type: string, payload: unknown): Event {
  return {
    action_type,
    payload,
  } as unknown as Event;
}

describe("parseSynthesis — claim provenance for named-source render", () => {
  it("carries each claim's supporting chunk ids (no count synthesised)", () => {
    const synth = parseSynthesis([
      ev("investigation.start_requested", { question: "Why X?" }),
      ev("synthesize.delivered", {
        thesis_summary: "Because Y.",
        implicit_recommendation: "proceed",
        thesis_components: [
          {
            claim: "Y holds.",
            confidence: "high",
            supporting_chunk_ids: ["chunk-a", "chunk-b"],
          },
        ],
        falsification_conditions: [],
        execution_risks: [],
        constraint_compliance: { hard_constraints_satisfied: true },
      }),
    ]);
    expect(synth).not.toBeNull();
    const claim = synth!.components[0];
    // The viewer needs the raw chunk ids to resolve named sources; the
    // parser does not invent "[2 chunks]".
    expect(claim.chunkIds).toEqual(["chunk-a", "chunk-b"]);
    expect(claim.claim).toBe("Y holds.");
    // chunkCitations maps chunk → citing component indices for the modal.
    expect(synth!.chunkCitations["chunk-a"]).toEqual([1]);
  });

  it("returns null when there is no synthesis yet (caller falls back)", () => {
    expect(
      parseSynthesis([ev("investigation.start_requested", { question: "Q" })]),
    ).toBeNull();
  });
});

// ── SPR-11 M3 — the inline-rubric verdict, READ (not recomputed) ──

describe("parseSynthesis — inline-rubric quality score (M3)", () => {
  function withRubric(extra: Event[]): ReturnType<typeof parseSynthesis> {
    return parseSynthesis([
      ev("investigation.start_requested", { question: "Why X?" }),
      ev("synthesize.delivered", {
        thesis_summary: "Because Y.",
        implicit_recommendation: "proceed",
        thesis_components: [],
        falsification_conditions: [],
        execution_risks: [],
        constraint_compliance: { hard_constraints_satisfied: true },
      }),
      ...extra,
    ]);
  }

  it("reads the composite + sub-scores from the persisted rubric.scored note", () => {
    const synth = withRubric([
      ev("rubric.scored", {
        final_score: 0.71,
        notes:
          "voice=0.80 conviction=0.50 citation_density=1.00 constraint=1.00",
      }),
    ]);
    expect(synth!.qualityScore).not.toBeNull();
    expect(synth!.qualityScore!.composite).toBeCloseTo(0.71);
    expect(synth!.qualityScore!.voiceStyle).toBeCloseTo(0.8);
    expect(synth!.qualityScore!.conviction).toBeCloseTo(0.5);
    expect(synth!.qualityScore!.citationDensity).toBeCloseTo(1.0);
    expect(synth!.qualityScore!.constraintCompliance).toBeCloseTo(1.0);
  });

  it("leaves sub-scores null for a free-form note (no fabricated breakdown)", () => {
    const synth = withRubric([
      ev("rubric.scored", {
        final_score: 0.1,
        notes: "synthesizer declined to produce a thesis (insufficient_evidence)",
      }),
    ]);
    expect(synth!.qualityScore!.composite).toBeCloseTo(0.1);
    expect(synth!.qualityScore!.voiceStyle).toBeNull();
    expect(synth!.qualityScore!.constraintCompliance).toBeNull();
  });

  it("leaves qualityScore null when no rubric event was persisted (absent)", () => {
    const synth = withRubric([]);
    expect(synth!.qualityScore).toBeNull();
  });

  it("ignores a malformed rubric event with no numeric final_score", () => {
    const synth = withRubric([
      ev("rubric.scored", { notes: "voice=0.80" }),
    ]);
    expect(synth!.qualityScore).toBeNull();
  });
});

// ── SPR-10 M2 — reuse provenance, READ from knowledge.reused (never invented) ──

describe("parseSynthesis — reuse provenance (SPR-10 M2)", () => {
  function withReuse(extra: Event[]): ReturnType<typeof parseSynthesis> {
    return parseSynthesis([
      ev("investigation.start_requested", { question: "Why X?" }),
      ev("synthesize.delivered", {
        thesis_summary: "Because Y.",
        implicit_recommendation: "proceed",
        thesis_components: [],
        falsification_conditions: [],
        execution_risks: [],
        constraint_compliance: { hard_constraints_satisfied: true },
      }),
      ...extra,
    ]);
  }

  it("parses two reused units into a two-entry reuseProvenance with EXACT ids (non-vacuity)", () => {
    const synth = withReuse([
      ev("knowledge.reused", {
        action_type: "knowledge.reused",
        reused_unit_ids: ["unit-aaa", "unit-bbb"],
        scores: [0.91, 0.83],
        // decisions describes EVERY retrieved unit (injected + dropped); the
        // parser reads only the injected set via reused_unit_ids/scores/sources.
        decisions: ["injected", "injected", "dropped-low-relevance"],
        source_investigation_ids: ["inv-src-1", "inv-src-2"],
        context_pack_event_id: "evt-pack-1",
      }),
    ]);
    expect(synth!.reuseProvenance).toHaveLength(2);
    // Non-vacuity: the EXACT ids/sources/scores, not just length 2.
    expect(synth!.reuseProvenance[0]).toEqual({
      unitId: "unit-aaa",
      sourceInvestigationId: "inv-src-1",
      score: 0.91,
    });
    expect(synth!.reuseProvenance[1]).toEqual({
      unitId: "unit-bbb",
      sourceInvestigationId: "inv-src-2",
      score: 0.83,
    });
  });

  it("unions reused units across MORE THAN ONE knowledge.reused event (encounter order)", () => {
    const synth = withReuse([
      ev("knowledge.reused", {
        reused_unit_ids: ["unit-1"],
        scores: [0.9],
        source_investigation_ids: ["inv-a"],
        context_pack_event_id: "evt-1",
      }),
      ev("knowledge.reused", {
        reused_unit_ids: ["unit-2", "unit-3"],
        scores: [0.8, 0.7],
        source_investigation_ids: ["inv-b", "inv-c"],
        context_pack_event_id: "evt-2",
      }),
    ]);
    expect(synth!.reuseProvenance.map((r) => r.unitId)).toEqual([
      "unit-1",
      "unit-2",
      "unit-3",
    ]);
  });

  it("invents nothing for a shorter parallel array (missing source/score → null)", () => {
    const synth = withReuse([
      ev("knowledge.reused", {
        reused_unit_ids: ["unit-x", "unit-y"],
        scores: [0.5], // only one score for two units
        source_investigation_ids: [], // no sources recorded
        context_pack_event_id: "evt-1",
      }),
    ]);
    expect(synth!.reuseProvenance[0]).toEqual({
      unitId: "unit-x",
      sourceInvestigationId: null,
      score: 0.5,
    });
    expect(synth!.reuseProvenance[1]).toEqual({
      unitId: "unit-y",
      sourceInvestigationId: null,
      score: null,
    });
  });

  it("yields an EMPTY reuseProvenance when no knowledge.reused event is present", () => {
    const synth = withReuse([]);
    expect(synth!.reuseProvenance).toEqual([]);
  });

  it("yields an EMPTY reuseProvenance for a reuse-of-nothing event (still emitted, no units)", () => {
    const synth = withReuse([
      ev("knowledge.reused", {
        reused_unit_ids: [],
        scores: [],
        source_investigation_ids: [],
        context_pack_event_id: "evt-1",
      }),
    ]);
    expect(synth!.reuseProvenance).toEqual([]);
  });

  it("marks only reused units listed in stale_advisory_unit_ids for refresh", () => {
    const synth = withReuse([
      ev("knowledge.reused", {
        reused_unit_ids: ["unit-current", "unit-stale"],
        scores: [0.92, 0.81],
        source_investigation_ids: ["inv-current", "inv-stale"],
        stale_advisory_unit_ids: ["unit-stale"],
        context_pack_event_id: "evt-1",
      }),
    ]);
    expect(synth!.reuseProvenance[0].staleRefreshAdvisory).toBeUndefined();
    expect(synth!.reuseProvenance[1]).toMatchObject({
      unitId: "unit-stale",
      staleRefreshAdvisory: true,
    });
  });

  it("attaches accepted stale-refresh child results by unit and source investigation", () => {
    const synth = withReuse([
      ev("knowledge.reused", {
        reused_unit_ids: ["unit-stale", "unit-other"],
        scores: [0.81, 0.75],
        source_investigation_ids: ["inv-source", "inv-other"],
        stale_advisory_unit_ids: ["unit-stale"],
        context_pack_event_id: "evt-1",
      }),
      ev("stale_reuse.refresh.accepted", {
        action_type: "stale_reuse.refresh.accepted",
        unit_id: "unit-stale",
        source_investigation_id: "inv-source",
        refresh_investigation_id: "inv-refresh",
        status: "refreshed",
        summary: "Source claim remains current after refresh.",
      }),
      ev("stale_reuse.refresh.promotion_candidate", {
        action_type: "stale_reuse.refresh.promotion_candidate",
        unit_id: "unit-stale",
        source_investigation_id: "inv-source",
        refresh_investigation_id: "inv-refresh",
        summary: "Source claim remains current after refresh.",
        supporting_chunk_ids: ["chunk-a", "chunk-b", 7],
      }),
      ev("stale_reuse.refresh.promotion_result", {
        action_type: "stale_reuse.refresh.promotion_result",
        unit_id: "unit-stale",
        source_investigation_id: "inv-source",
        refresh_investigation_id: "inv-refresh",
        status: "deposited",
        reason: "ready",
        deposited_node_id: "node-refreshed",
        primary_chunk_id: "chunk-a",
        primary_source_document_id: "doc-refresh",
        unresolved_chunk_ids: [9],
      }),
    ]);

    expect(synth!.reuseProvenance[0].acceptedRefresh).toEqual({
      refreshInvestigationId: "inv-refresh",
      status: "refreshed",
      summary: "Source claim remains current after refresh.",
    });
    expect(synth!.reuseProvenance[0].refreshPromotionCandidate).toEqual({
      refreshInvestigationId: "inv-refresh",
      summary: "Source claim remains current after refresh.",
      supportingChunkIds: ["chunk-a", "chunk-b"],
    });
    expect(synth!.reuseProvenance[0].refreshPromotionResult).toEqual({
      refreshInvestigationId: "inv-refresh",
      status: "deposited",
      reason: "ready",
      depositedNodeId: "node-refreshed",
      primaryChunkId: "chunk-a",
      primarySourceDocumentId: "doc-refresh",
      unresolvedChunkIds: [],
    });
    expect(synth!.reuseProvenance[1].acceptedRefresh).toBeUndefined();
    expect(synth!.reuseProvenance[1].refreshPromotionCandidate).toBeUndefined();
    expect(synth!.reuseProvenance[1].refreshPromotionResult).toBeUndefined();
  });
});

// ── SPR-10 M4 — the per-run compounding stat (real `reused`, honest nulls) ──

describe("parseSynthesis — compounding stat (SPR-10 M4)", () => {
  function withEvents(extra: Event[]): ReturnType<typeof parseSynthesis> {
    return parseSynthesis([
      ev("investigation.start_requested", { question: "Why X?" }),
      ev("synthesize.delivered", {
        thesis_summary: "Because Y.",
        implicit_recommendation: "proceed",
        thesis_components: [],
        falsification_conditions: [],
        execution_risks: [],
        constraint_compliance: { hard_constraints_satisfied: true },
      }),
      ...extra,
    ]);
  }

  it("compoundingStat is null when nothing was reused and no measurement exists", () => {
    const synth = withEvents([]);
    expect(synth).not.toBeNull();
    expect(synth!.compoundingStat).toBeNull();
  });

  it("compoundingStat stays NULL with reuse but no measurement (M4: null when no measurement)", () => {
    const synth = withEvents([
      ev("knowledge.reused", {
        reused_unit_ids: ["u1", "u2"],
        scores: [0.9, 0.8],
        source_investigation_ids: ["inv-a", "inv-b"],
        context_pack_event_id: "evt-1",
      }),
    ]);
    // The stat is gated on a per-run MEASUREMENT event (none exists here). The
    // reused count is surfaced by reuseProvenance (M3's list), never synthesized
    // into a stat line — a stat without a measurement would imply one happened.
    expect(synth!.reuseProvenance).toHaveLength(2);
    expect(synth!.compoundingStat).toBeNull();
  });

  // Non-vacuity / seed-and-catch: a SYNTHETIC per-run measurement event (a shape
  // the substrate does NOT emit today — there is no compounding.measured
  // ActionType) drives the full three-number render path so it is provably
  // non-vacuous. The real-data path stays null (the test above).
  it("reads the three exact numbers from a synthetic compounding.measured event", () => {
    const synth = withEvents([
      ev("compounding.measured", {
        reused: 3,
        avoided: 2,
        fewer_sources: 5,
      }),
    ]);
    expect(synth!.compoundingStat).toEqual({
      reused: 3,
      avoided: 2,
      fewerSources: 5,
    });
  });
});
