import { describe, expect, it } from "vitest";
import { twinPromoteContextReadiness } from "./twinPromoteContextReadiness";

describe("twinPromoteContextReadiness (aum)", () => {
  it("allows promote when twins not yet hydrated", () => {
    const r = twinPromoteContextReadiness({
      twins_hydrated: false,
      promote_kinds: "all",
    });
    expect(r.promote_ready).toBe(true);
    expect(r.twins_hydrated).toBe(false);
    expect(r.summary).toMatch(/unknown/i);
  });

  it("gates all by non-empty substrate after hydrate", () => {
    expect(
      twinPromoteContextReadiness({
        twins_hydrated: true,
        promote_kinds: "all",
        substrate: { empty: true, has_insights: false, has_questions: false },
      }).promote_ready,
    ).toBe(false);
    expect(
      twinPromoteContextReadiness({
        twins_hydrated: true,
        promote_kinds: "all",
        substrate: { empty: false, has_insights: true, has_questions: false },
      }).promote_ready,
    ).toBe(true);
  });

  it("gates kind filters by leg presence", () => {
    const insightOnly = {
      empty: false,
      has_insights: true,
      has_questions: false,
    };
    expect(
      twinPromoteContextReadiness({
        twins_hydrated: true,
        promote_kinds: "insight",
        substrate: insightOnly,
      }).promote_ready,
    ).toBe(true);
    expect(
      twinPromoteContextReadiness({
        twins_hydrated: true,
        promote_kinds: "question",
        substrate: insightOnly,
      }).promote_ready,
    ).toBe(false);
    expect(
      twinPromoteContextReadiness({
        twins_hydrated: true,
        promote_kinds: "question",
        substrate: insightOnly,
      }).disabled_title,
    ).toMatch(/No question twins/i);
  });
});
