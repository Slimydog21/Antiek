import { describe, expect, it } from "vitest";
import {
  CITATION_HOP_PIPELINE_STAGES,
  COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES,
  COMPETITIVE_DR_PIPELINE_STAGES,
  citationHopStageProgress,
  competitiveDrOfflineSurfaceCatalog,
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

  it("ships closed offline product surface catalog (arm)", () => {
    expect(COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES.length).toBeGreaterThanOrEqual(
      10,
    );
    expect(COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES).toContain(
      "notdiamond_advisory_never_router",
    );
    expect(COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES).toContain(
      "midnight_oil_goals_duration_ceiling",
    );
    // Residual (art): twin substrate + L5 receipt surfaces.
    expect(COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES).toContain(
      "twin_substrate_insights_questions",
    );
    // Residual (ash): asb–asg readiness→CTA competitive surfaces.
    expect(COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES).toContain(
      "publication_attach_readiness",
    );
    expect(COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES).toContain(
      "decision_tree_install_model_gate",
    );
    expect(COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES).toContain(
      "written_analysis_multi_agent_path",
    );
    expect(COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES).toContain(
      "readiness_cta_free_host_twin_path_moil",
    );
    // Residual (asr): highlight→DR launch readiness (asq).
    expect(COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES).toContain(
      "highlight_dr_launch_readiness",
    );
    expect(COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES).toContain(
      "marketplace_l5_receipt_readiness",
    );
    expect(COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES).toContain(
      "marketplace_free_host_readiness",
    );
    const cat = competitiveDrOfflineSurfaceCatalog();
    expect(cat.live_injectors_deferred).toBe(true);
    expect(cat.notdiamond_is_router).toBe(false);
    expect(cat.count).toBe(COMPETITIVE_DR_OFFLINE_PRODUCT_SURFACES.length);
    expect(cat.count).toBeGreaterThanOrEqual(14);
    expect(cat.summary).toMatch(/offline product surfaces/i);
    expect(cat.summary).toMatch(/ND never router/i);
  });
});
