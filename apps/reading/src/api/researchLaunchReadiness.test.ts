import { describe, expect, it } from "vitest";
import {
  evaluateResearchLaunchReadiness,
  formatLaunchReadinessSummary,
} from "./researchLaunchReadiness";

describe("evaluateResearchLaunchReadiness", () => {
  it("launch_ready when sources quality budget ok", () => {
    const d = evaluateResearchLaunchReadiness({
      session_id: "sess-1",
      source_family_count: 2,
      quality_overall: 0.8,
      quality_floor: 0.5,
      would_exceed: false,
    });
    expect(d.launch_ready).toBe(true);
    expect(d.live_dispatch_authorized).toBe(false);
    expect(d.sources_ready).toBe(true);
    expect(d.budget_ready).toBe(true);
  });

  it("fails sources when count 0", () => {
    const d = evaluateResearchLaunchReadiness({
      session_id: "sess-1",
      source_family_count: 0,
      quality_overall: 0.9,
      would_exceed: false,
    });
    expect(d.sources_ready).toBe(false);
    expect(d.launch_ready).toBe(false);
    expect(d.live_dispatch_authorized).toBe(false);
  });

  it("would_exceed null fail closed without override", () => {
    const d = evaluateResearchLaunchReadiness({
      session_id: "sess-1",
      source_family_count: 1,
      quality_overall: null,
      would_exceed: null,
    });
    expect(d.budget_ready).toBe(false);
    expect(d.launch_ready).toBe(false);
  });

  it("would_exceed null with override allows budget_ready", () => {
    const d = evaluateResearchLaunchReadiness({
      session_id: "sess-1",
      source_family_count: 1,
      quality_overall: null,
      would_exceed: null,
      operator_override: true,
    });
    expect(d.budget_ready).toBe(true);
    expect(d.launch_ready).toBe(true);
    expect(d.live_dispatch_authorized).toBe(false);
  });

  it("quality below floor blocks", () => {
    const d = evaluateResearchLaunchReadiness({
      session_id: "sess-1",
      source_family_count: 1,
      quality_overall: 0.2,
      quality_floor: 0.5,
      would_exceed: false,
    });
    expect(d.quality_ready).toBe(false);
    expect(d.launch_ready).toBe(false);
  });

  it("rejects non-integer source count", () => {
    expect(() =>
      evaluateResearchLaunchReadiness({
        session_id: "s",
        source_family_count: 1.5,
        quality_overall: null,
        would_exceed: false,
      }),
    ).toThrow(/integer/);
  });
});

describe("formatLaunchReadinessSummary", () => {
  it("summarizes honesty", () => {
    const d = evaluateResearchLaunchReadiness({
      session_id: "s",
      source_family_count: 1,
      quality_overall: null,
      would_exceed: false,
    });
    expect(formatLaunchReadinessSummary(d)).toMatch(
      /live_dispatch_authorized=false/,
    );
  });
});
