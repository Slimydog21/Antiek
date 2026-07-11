import { describe, expect, it } from "vitest";
import {
  composeResearchWorkstationFullLoop,
  formatResearchWorkstationFullLoopSummary,
} from "./researchWorkstationFullLoopSupercompose";

const wrestleReady = {
  session_id: "ws-1",
  parent_asset_id: "asset-1",
  floating_instance_count: 2,
  completed_floating_count: 1,
  twin_insight_count: 2,
  twin_question_count: 1,
  open_question_count: 1,
  source_family_count: 2,
  citation_pack_ready: true,
  quality_overall: 0.8,
  would_exceed: false as boolean | null,
  preferred_view_mode: "floating" as const,
};

describe("composeResearchWorkstationFullLoop", () => {
  it("is full_loop_ready when all gates pass and never dispatches", () => {
    const c = composeResearchWorkstationFullLoop({
      wrestle: wrestleReady,
      source_attach: {
        attach_ready: true,
        remote_fetched: false,
        source_count: 2,
      },
      view_mode: {
        preferred_view_mode: "fullscreen",
        floating_instance_count: 2,
      },
      budget: { would_exceed: false, selected_model_id: "gpt-5" },
    });
    expect(c.full_loop_ready).toBe(true);
    expect(c.wrestle.wrestle_ready).toBe(true);
    expect(c.source_attach_ready).toBe(true);
    expect(c.view_mode_ready).toBe(true);
    expect(c.budget_ready).toBe(true);
    expect(c.live_dispatch_authorized).toBe(false);
    expect(c.authority).toBe(
      "research_workstation_full_loop_supercompose_advisory",
    );
    expect(formatResearchWorkstationFullLoopSummary(c)).toMatch(
      /live_dispatch_authorized=false/,
    );
  });

  it("not ready without source attach", () => {
    const c = composeResearchWorkstationFullLoop({
      wrestle: wrestleReady,
      source_attach: {
        attach_ready: false,
        remote_fetched: false,
        source_count: 0,
      },
      view_mode: {
        preferred_view_mode: "floating",
        floating_instance_count: 1,
      },
      budget: { would_exceed: false },
    });
    expect(c.source_attach_ready).toBe(false);
    expect(c.full_loop_ready).toBe(false);
    expect(c.live_dispatch_authorized).toBe(false);
  });

  it("rejects remote_fetched true", () => {
    expect(() =>
      composeResearchWorkstationFullLoop({
        wrestle: wrestleReady,
        source_attach: {
          attach_ready: true,
          // @ts-expect-error intentional
          remote_fetched: true,
          source_count: 1,
        },
        view_mode: {
          preferred_view_mode: null,
          floating_instance_count: 1,
        },
        budget: { would_exceed: false },
      }),
    ).toThrow(/remote_fetched/);
  });
});
