import { describe, expect, it } from "vitest";
import {
  CITATION_HOP_PIPELINE_STAGES,
  COMPETITIVE_DR_PIPELINE_STAGES,
  citationHopStageProgress,
  competitiveDrStageProgress,
  competitiveDrWorldClassReadiness,
  normalizeCompetitiveDrStage,
} from "./competitiveDrQuality";

describe("competitiveDrQuality workspace pure helpers (apw)", () => {
  it("exports closed pipeline stage lists", () => {
    expect([...COMPETITIVE_DR_PIPELINE_STAGES]).toEqual([
      "plan",
      "gather",
      "synthesize",
      "cite",
      "terminal",
    ]);
    expect([...CITATION_HOP_PIPELINE_STAGES]).toEqual([
      "insights",
      "questions",
      "sources",
    ]);
  });

  it("normalizes stages and derives multi-stage progress without inventing", () => {
    expect(normalizeCompetitiveDrStage("citation pass")).toBe("cite");
    const mid = competitiveDrStageProgress({
      events: [{ stage: "plan" }, { stage: "gather" }],
      latest_stage: "gather",
    });
    expect(mid.completed_count).toBe(2);
    expect(mid.completed).toEqual(["plan", "gather"]);
  });

  it("derives hop progress without inventing empty hops", () => {
    const hop = citationHopStageProgress({
      insight_count: 1,
      question_count: 0,
      ref_count: 1,
    });
    expect(hop.present).toEqual(["insights", "sources"]);
    expect(hop.missing).toEqual(["questions"]);
    expect(hop.coverage_ratio).toBeCloseTo(2 / 3);
  });

  it("combines world-class readiness without inventing hop coverage", () => {
    const wc = competitiveDrWorldClassReadiness({
      stage_coverage_ratio: 0.8,
      hop_coverage_ratio: null,
    });
    expect(wc.world_class_bar).toBe("multi_stage");
    expect(wc.citation_hops_ready).toBeNull();

    const both = competitiveDrWorldClassReadiness({
      stage_coverage_ratio: 1,
      hop_coverage_ratio: 1,
      stage_is_terminal: true,
    });
    expect(both.world_class_bar).toBe("multi_stage_and_hops");
  });
});
