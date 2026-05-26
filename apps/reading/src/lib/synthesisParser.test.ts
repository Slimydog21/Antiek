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
