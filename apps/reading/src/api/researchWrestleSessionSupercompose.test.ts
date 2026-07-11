import { describe, expect, it } from "vitest";
import {
  composeResearchWrestleSession,
  formatResearchWrestleSessionSummary,
} from "./researchWrestleSessionSupercompose";

const readyBase = {
  session_id: "ws-1",
  parent_asset_id: "asset-1",
  floating_instance_count: 2,
  completed_floating_count: 1,
  twin_insight_count: 3,
  twin_question_count: 2,
  open_question_count: 1,
  source_family_count: 2,
  citation_pack_ready: true,
  quality_overall: 0.8,
  would_exceed: false as boolean | null,
  preferred_view_mode: "floating" as const,
};

describe("composeResearchWrestleSession", () => {
  it("is wrestle_ready when all gates pass and never authorizes dispatch", () => {
    const s = composeResearchWrestleSession(readyBase);
    expect(s.wrestle_ready).toBe(true);
    expect(s.floating_ready).toBe(true);
    expect(s.twin_ready).toBe(true);
    expect(s.sources_ready).toBe(true);
    expect(s.quality_ready).toBe(true);
    expect(s.budget_ready).toBe(true);
    expect(s.citation_ready).toBe(true);
    expect(s.live_dispatch_authorized).toBe(false);
    expect(s.authority).toBe("research_wrestle_session_supercompose_advisory");
    expect(formatResearchWrestleSessionSummary(s)).toMatch(
      /live_dispatch_authorized=false/,
    );
  });

  it("not ready without sources or quality", () => {
    const noSrc = composeResearchWrestleSession({
      ...readyBase,
      source_family_count: 0,
    });
    expect(noSrc.sources_ready).toBe(false);
    expect(noSrc.wrestle_ready).toBe(false);
    expect(noSrc.live_dispatch_authorized).toBe(false);

    const lowQ = composeResearchWrestleSession({
      ...readyBase,
      quality_overall: 0.2,
      quality_floor: 0.5,
    });
    expect(lowQ.quality_ready).toBe(false);
    expect(lowQ.wrestle_ready).toBe(false);
  });

  it("budget unknown fails closed unless override", () => {
    const unk = composeResearchWrestleSession({
      ...readyBase,
      would_exceed: null,
    });
    expect(unk.budget_ready).toBe(false);
    expect(unk.wrestle_ready).toBe(false);

    const ov = composeResearchWrestleSession({
      ...readyBase,
      would_exceed: null,
      operator_override: true,
    });
    expect(ov.budget_ready).toBe(true);
    expect(ov.wrestle_ready).toBe(true);
    expect(ov.live_dispatch_authorized).toBe(false);
  });

  it("rejects completed > floating and bad view mode", () => {
    expect(() =>
      composeResearchWrestleSession({
        ...readyBase,
        floating_instance_count: 1,
        completed_floating_count: 2,
      }),
    ).toThrow(/completed_floating_count/);
    expect(() =>
      composeResearchWrestleSession({
        ...readyBase,
        // @ts-expect-error intentional
        preferred_view_mode: "merged_full",
      }),
    ).toThrow(/preferred_view_mode/);
  });

  it("substrate from twin/questions without floating can still be ready", () => {
    const s = composeResearchWrestleSession({
      ...readyBase,
      floating_instance_count: 0,
      completed_floating_count: 0,
      twin_insight_count: 1,
      twin_question_count: 0,
      open_question_count: 0,
    });
    expect(s.floating_ready).toBe(false);
    expect(s.twin_ready).toBe(true);
    expect(s.wrestle_ready).toBe(true);
    expect(s.live_dispatch_authorized).toBe(false);
  });
});
