import { describe, expect, it } from "vitest";
import { parseDeepResearchSessionProjection, parseDeepResearchSessionResumeRef } from "./deepResearchSessionRefs";

const projection = { schema_version: 1, session_id: "session", spawn_id: "spawn", investigation_id: "inv", parent_asset_id: "asset", status: "running", research_tier: "deep", view_format: "html" };

describe("deep research session reference parser", () => {
  it("accepts only the exact reference", () => {
    expect(parseDeepResearchSessionResumeRef({ session_id: "session" })).toEqual({ session_id: "session" });
    expect(parseDeepResearchSessionResumeRef({ session_id: "session", goal: "forged" })).toBeNull();
  });
  it("accepts only the exact runtime projection", () => {
    expect(parseDeepResearchSessionProjection(projection)).toEqual(projection);
    for (const forged of ["selection_text", "goal", "model_id", "citation_provenance", "html", "output_text"]) {
      expect(() => parseDeepResearchSessionProjection({ ...projection, [forged]: "secret" })).toThrow();
    }
    expect(() => parseDeepResearchSessionProjection({ ...projection, status: "unknown" })).toThrow();
  });
});
