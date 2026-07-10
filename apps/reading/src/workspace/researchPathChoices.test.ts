import { describe, expect, it } from "vitest";

import { researchPathChoicesReadiness } from "./researchPathChoices";

describe("researchPathChoicesReadiness residual (aqy)", () => {
  it("is not ready when parent and selection are empty", () => {
    const r = researchPathChoicesReadiness({});
    expect(r.parent_bound).toBe(false);
    expect(r.spawn_or_selection_ready).toBe(false);
    expect(r.float_full_ready).toBe(false);
    expect(r.draft_merge_ready).toBe(false);
    expect(r.into_parent_ready).toBe(false);
    expect(r.written_analysis_ready).toBe(false);
    expect(r.selected_count).toBe(0);
    expect(r.summary).toMatch(/bind parent/i);
  });

  it("requires parent + ≥1 spawn for draft and into-parent", () => {
    expect(
      researchPathChoicesReadiness({
        parentAssetId: "book-1",
        selectedCount: 0,
      }).draft_merge_ready,
    ).toBe(false);
    expect(
      researchPathChoicesReadiness({
        parentAssetId: "book-1",
        selectedCount: 1,
      }).draft_merge_ready,
    ).toBe(true);
    expect(
      researchPathChoicesReadiness({
        parentAssetId: "book-1",
        selectedCount: 1,
      }).into_parent_ready,
    ).toBe(true);
    expect(
      researchPathChoicesReadiness({
        parentAssetId: "book-1",
        selectedCount: 1,
      }).written_analysis_ready,
    ).toBe(false);
  });

  it("requires ≥2 spawns for written analysis by default", () => {
    const one = researchPathChoicesReadiness({
      parentAssetId: "book-1",
      selectedCount: 1,
    });
    expect(one.written_analysis_ready).toBe(false);
    expect(one.summary).toMatch(/1 selected/i);
    const two = researchPathChoicesReadiness({
      parentAssetId: "book-1",
      selectedCount: 2,
    });
    expect(two.written_analysis_ready).toBe(true);
    expect(two.summary).toMatch(/written analysis ready/i);
  });

  it("stamps float_full_ready only when session bound", () => {
    expect(
      researchPathChoicesReadiness({ sessionBound: true }).float_full_ready,
    ).toBe(true);
    expect(
      researchPathChoicesReadiness({ sessionBound: false }).float_full_ready,
    ).toBe(false);
  });

  it("never invents readiness from whitespace parent", () => {
    const r = researchPathChoicesReadiness({
      parentAssetId: "   ",
      selectedCount: 3,
    });
    expect(r.parent_bound).toBe(false);
    expect(r.draft_merge_ready).toBe(false);
    expect(r.written_analysis_ready).toBe(false);
  });
});
