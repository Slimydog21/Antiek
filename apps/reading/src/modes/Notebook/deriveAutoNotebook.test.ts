/**
 * deriveAutoNotebook.test.ts — SPR-06 M1, the PURE derivation behind the
 * auto-notebook (PROPOSED — sign-off pending).
 *
 * Pins the load-bearing gates as deterministic pure-function assertions
 * (no async, no DOM): the graph-change re-derive (M1), rigor #1 (only real
 * graph content, honest empty), and the synthesis-section gating that the
 * §9.0 servable guard relies on (a synthesis section is emitted only when the
 * graph carries a real synthesis — its BODY is rendered downstream by
 * MasterMdViewer, which owns the §9.0 no-leak).
 */
import { describe, expect, it } from "vitest";

import type { DistilledNode } from "../../lib/api";
import type { ParsedSynthesis } from "../../lib/synthesisParser";
import { deriveAutoNotebook } from "./deriveAutoNotebook";

function insight(node_id: string, text: string): DistilledNode {
  return {
    node_id,
    kind: "insight",
    text,
    confidence: "high",
    source_document_id: "doc-1",
    refinement_count: 0,
    escalated: false,
    reserved_child_investigation_id: null,
  };
}
function question(
  node_id: string,
  text: string,
  escalated = false,
): DistilledNode {
  return {
    node_id,
    kind: "question",
    text,
    confidence: null,
    source_document_id: null,
    refinement_count: 0,
    escalated,
    reserved_child_investigation_id: null,
  };
}

function synthesisWith(thesis: string): ParsedSynthesis {
  return {
    investigationId: "inv-1",
    synthesisId: null,
    thesisSummary: thesis,
    components: [],
    falsificationConditions: [],
    executionRisks: [],
    recommendation: "undetermined",
    hardConstraintsSatisfied: null,
    totalCostUsd: 0,
    question: "What is the moat?",
    masterMdPath: null,
    domainsPatched: [],
    chunkCitations: {},
    qualityScore: null,
    reuseProvenance: [],
    compoundingStat: null,
    staleResolutionsByEntityId: {},
  };
}

describe("deriveAutoNotebook — only real graph content (rigor #1)", () => {
  it("derives an honest EMPTY notebook when the graph carries nothing", () => {
    const nb = deriveAutoNotebook({
      investigationId: "inv-1",
      question: null,
      insights: [],
      questions: [],
      synthesis: null,
    });
    expect(nb.isEmpty).toBe(true);
    expect(nb.outline).toHaveLength(0);
    expect(nb.synthesis).toBeNull();
    // No fabricated title — the honest fallback, never an invented question.
    expect(nb.title).toBe("This research");
  });

  it("emits a section ONLY for graph data that exists — never a fabricated one", () => {
    const nb = deriveAutoNotebook({
      investigationId: "inv-1",
      question: "What is the moat?",
      insights: [insight("i1", "GPUs gate scale.")],
      questions: [],
      synthesis: null, // no synthesis → NO synthesis section
    });
    const kinds = nb.outline.map((s) => s.kind);
    expect(kinds).toEqual(["insights"]);
    expect(kinds).not.toContain("synthesis");
    expect(kinds).not.toContain("questions");
    expect(nb.outline[0].entries.map((e) => e.text)).toEqual([
      "GPUs gate scale.",
    ]);
  });

  it("does NOT emit a synthesis section for an empty/contentless synthesis", () => {
    const nb = deriveAutoNotebook({
      investigationId: "inv-1",
      question: "What is the moat?",
      insights: [],
      questions: [question("q1", "Where is the moat?")],
      synthesis: synthesisWith("   "), // whitespace thesis, no components
    });
    expect(nb.outline.map((s) => s.kind)).toEqual(["questions"]);
    expect(nb.synthesis).toBeNull();
  });
});

describe("deriveAutoNotebook — re-derives on graph change (M1 load-bearing)", () => {
  it("flips the outline + sections when an insight is added to the graph", () => {
    // BEFORE: distillation = [insight A, question B].
    const before = deriveAutoNotebook({
      investigationId: "inv-1",
      question: "What is the moat?",
      insights: [insight("A", "Insight A.")],
      questions: [question("B", "Question B?")],
      synthesis: null,
    });
    expect(before.outline.map((s) => s.kind)).toEqual([
      "insights",
      "questions",
    ]);
    expect(
      before.outline.find((s) => s.kind === "insights")!.entries.map((e) => e.text),
    ).toEqual(["Insight A."]);

    // AFTER: add insight C (the graph changed). The SAME pure function over the
    // new graph state flips the rendered sections — the insights section now
    // carries A AND C. This is the dynamic re-derive: the React wrapper re-runs
    // this on the event-stream change.
    const after = deriveAutoNotebook({
      investigationId: "inv-1",
      question: "What is the moat?",
      insights: [insight("A", "Insight A."), insight("C", "Insight C.")],
      questions: [question("B", "Question B?")],
      synthesis: null,
    });
    const afterInsights = after.outline
      .find((s) => s.kind === "insights")!
      .entries.map((e) => e.text);
    expect(afterInsights).toEqual(["Insight A.", "Insight C."]);
    // The outline genuinely differs from before (the re-derive is observable).
    expect(afterInsights).not.toEqual(["Insight A."]);
  });

  it("a synthesis settling adds the synthesis section to the outline", () => {
    const beforeSynth = deriveAutoNotebook({
      investigationId: "inv-1",
      question: "What is the moat?",
      insights: [insight("A", "Insight A.")],
      questions: [],
      synthesis: null,
    });
    expect(beforeSynth.outline.map((s) => s.kind)).toEqual(["insights"]);

    const afterSynth = deriveAutoNotebook({
      investigationId: "inv-1",
      question: "What is the moat?",
      insights: [insight("A", "Insight A.")],
      questions: [],
      synthesis: synthesisWith("The moat is data scale."),
    });
    // Synthesis section now leads; the outline flipped.
    expect(afterSynth.outline.map((s) => s.kind)).toEqual([
      "synthesis",
      "insights",
    ]);
    expect(afterSynth.synthesis).not.toBeNull();
  });
});

describe("deriveAutoNotebook — title + escalation are carried, not invented", () => {
  it("titles from the research question when the graph carries one", () => {
    const nb = deriveAutoNotebook({
      investigationId: "inv-1",
      question: "What is the moat?",
      insights: [insight("i1", "x")],
      questions: [],
      synthesis: null,
    });
    expect(nb.title).toBe("What is the moat?");
  });

  it("carries an escalated question's flag through to the entry", () => {
    const nb = deriveAutoNotebook({
      investigationId: "inv-1",
      question: null,
      insights: [],
      questions: [question("q1", "Unresolved?", true)],
      synthesis: null,
    });
    const q = nb.outline.find((s) => s.kind === "questions")!.entries[0];
    expect(q.escalated).toBe(true);
  });
});
