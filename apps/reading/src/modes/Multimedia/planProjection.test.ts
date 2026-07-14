import { describe, expect, it } from "vitest";

import type { MultimediaPlanWire } from "../../api/multimedia";
import { projectMultimediaPlan } from "./planProjection";

const PLAN: MultimediaPlanWire = {
  request: { topic: "Chip packaging", target_minutes: 15, mode: "video", route_policy: "balanced", depth: "intermediate", selected_arc_ids: [] },
  suggestions: [{
    arc_id: "mechanism",
    title: "Packaging mechanism",
    teaches: "How chiplets exchange data",
    evidence: [],
    tradeoff: "Omits manufacturing finance",
  }],
  chosen_arc_ids: ["mechanism"],
  chapters: [{
    chapter_id: "ch-mechanism",
    title: "The package is the system",
    minutes: 15,
    purpose: "Explain interconnect density.",
    arc_id: "mechanism",
    source_chunk_ids: ["chunk-1"],
    cuts: [],
  }],
  script_lines: [{
    line_id: "ch-mechanism-line-0",
    sequence: 0,
    text: "Interconnect density determines how chiplets cooperate.",
    kind: "factual",
    citations: [{ chunk_id: "chunk-1", document_id: "doc-packaging", locator: "§2", quote_sha256: null }],
    unsourced_reason: null,
  }],
  scenes: [{
    scene_id: "scene-1",
    chapter_id: "ch-mechanism",
    visual_intent: "Layered diagram",
    information_purpose: "Show interposer links",
    narration_line_ids: ["ch-mechanism-line-0"],
    source_chunk_ids: ["chunk-1"],
  }],
  omissions: ["Manufacturing finance is outside scope."],
  unsourced_line_ids: [],
  duration_tolerance_minutes: 0.25,
};

describe("projectMultimediaPlan", () => {
  it("projects exact curriculum, transcript, scenes, and citation identities", () => {
    const result = projectMultimediaPlan(PLAN);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.value.suggestions[0]).toContain("Packaging mechanism");
    expect(result.value.omissions).toEqual(["Manufacturing finance is outside scope."]);
    expect(result.value.chapters[0]).toMatchObject({
      id: "ch-mechanism",
      transcript: "Interconnect density determines how chiplets cooperate.",
      visualLabel: "diagram",
      sourceId: "chunk-1",
    });
    expect(result.value.sources).toEqual([{
      id: "chunk-1",
      title: "doc-packaging",
      status: "cited",
      detail: "§2",
    }]);
  });

  it("surfaces the server unsourced reason without inventing one", () => {
    const unsourced = structuredClone(PLAN);
    unsourced.script_lines[0].citations = [];
    unsourced.script_lines[0].unsourced_reason = "needs primary measurement";
    unsourced.unsourced_line_ids = ["ch-mechanism-line-0"];
    unsourced.chapters[0].source_chunk_ids = [];
    unsourced.scenes[0].source_chunk_ids = [];
    const result = projectMultimediaPlan(unsourced);
    expect(result.ok && result.value.unsourcedClaims).toEqual([
      "Interconnect density determines how chiplets cooperate. — needs primary measurement",
    ]);
  });

  it("rejects an uncited factual line omitted from the grounding ledger", () => {
    const plan = structuredClone(PLAN);
    plan.script_lines.push({
      line_id: "ch-mechanism-line-1",
      sequence: 1,
      text: "An unrecorded claim.",
      kind: "factual",
      citations: [],
      unsourced_reason: "needs a source",
    });

    expect(projectMultimediaPlan(plan)).toEqual({ ok: false, error: "Unsourced claim ledger conflicts." });
  });

  it("rejects malformed line kinds and dangling storyboard provenance", () => {
    const invalidKind = structuredClone(PLAN);
    invalidKind.script_lines[0].kind = "fact" as MultimediaPlanWire["script_lines"][number]["kind"];
    expect(projectMultimediaPlan(invalidKind)).toEqual({ ok: false, error: "Plan script identity conflicts." });

    const danglingScene = structuredClone(PLAN);
    danglingScene.scenes[0].narration_line_ids = ["missing-line"];
    expect(projectMultimediaPlan(danglingScene)).toEqual({ ok: false, error: "Storyboard scene identity conflicts." });
  });

  it.each([
    [{}, "chapters"],
    [{ ...PLAN, chapters: [] }, "grounding"],
    [{ ...PLAN, script_lines: [] }, "scene identity"],
    [{ ...PLAN, suggestions: [...PLAN.suggestions, PLAN.suggestions[0]] }, "coverage selection"],
    [{ ...PLAN, chosen_arc_ids: ["unknown"] }, "coverage selection"],
    [{ ...PLAN, scenes: [{ ...PLAN.scenes[0], chapter_id: "missing" }] }, "narration provenance"],
    [{ ...PLAN, unsourced_line_ids: ["missing"] }, "ledger conflicts"],
  ])("rejects malformed persisted plan %#", (value, message) => {
    const result = projectMultimediaPlan(value);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.toLowerCase()).toContain(message);
  });
});
