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
