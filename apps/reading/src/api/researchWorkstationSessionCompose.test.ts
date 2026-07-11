import { describe, expect, it } from "vitest";
import {
  composeResearchWorkstationSession,
  formatResearchWorkstationSessionSummary,
} from "./researchWorkstationSessionCompose";

const readyBase = {
  session_id: "sess-1",
  parent_asset_id: "asset-1",
  floating_instance_count: 1,
  twin_bound: true,
  source_family_count: 2,
  quality_overall: 0.8,
  quality_floor: 0.5,
  would_exceed: false as boolean | null,
  cohesive_pack_ready: false,
  operator_override: false,
};

describe("composeResearchWorkstationSession", () => {
  it("session ready without live dispatch", () => {
    const s = composeResearchWorkstationSession(readyBase);
    expect(s.session_ready).toBe(true);
    expect(s.live_dispatch_authorized).toBe(false);
    expect(s.sources_ready).toBe(true);
    expect(s.quality_ready).toBe(true);
    expect(s.budget_ready).toBe(true);
    expect(s.floating_ready).toBe(true);
    expect(s.twin_ready).toBe(true);
    expect(s.authority).toBe(
      "research_workstation_session_compose_advisory",
    );
    expect(formatResearchWorkstationSessionSummary(s)).toMatch(
      /live_dispatch_authorized=false/,
    );
  });

  it("requires cohesive pack when ≥2 floating", () => {
    const s = composeResearchWorkstationSession({
      ...readyBase,
      floating_instance_count: 2,
      cohesive_pack_ready: false,
    });
    expect(s.session_ready).toBe(false);
    expect(s.live_dispatch_authorized).toBe(false);
    expect(
      s.notes.some((n) => n.includes("cohesive_pack_ready")),
    ).toBe(true);
    const ready = composeResearchWorkstationSession({
      ...readyBase,
      floating_instance_count: 2,
      cohesive_pack_ready: true,
    });
    expect(ready.session_ready).toBe(true);
    expect(ready.live_dispatch_authorized).toBe(false);
  });

  it("would_exceed null fails budget without override", () => {
    const s = composeResearchWorkstationSession({
      ...readyBase,
      would_exceed: null,
    });
    expect(s.budget_ready).toBe(false);
    expect(s.session_ready).toBe(false);
    expect(s.live_dispatch_authorized).toBe(false);
    const over = composeResearchWorkstationSession({
      ...readyBase,
      would_exceed: null,
      operator_override: true,
    });
    expect(over.budget_ready).toBe(true);
    expect(over.live_dispatch_authorized).toBe(false);
  });

  it("quality unknown fails closed", () => {
    const s = composeResearchWorkstationSession({
      ...readyBase,
      quality_overall: null,
    });
    expect(s.quality_ready).toBe(false);
    expect(s.session_ready).toBe(false);
    expect(s.notes.some((n) => n.includes("no invent"))).toBe(true);
  });

  it("rejects blank ids and negative counts", () => {
    expect(() =>
      composeResearchWorkstationSession({
        ...readyBase,
        session_id: "  ",
      }),
    ).toThrow(/session_id/);
    expect(() =>
      composeResearchWorkstationSession({
        ...readyBase,
        floating_instance_count: -1,
      }),
    ).toThrow(/floating_instance_count/);
    expect(() =>
      composeResearchWorkstationSession({
        ...readyBase,
        twin_bound: "yes" as unknown as boolean,
      }),
    ).toThrow(/twin_bound/);
  });
});
