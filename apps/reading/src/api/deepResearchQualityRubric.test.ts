import { describe, expect, it } from "vitest";
import {
  evaluateDeepResearchQuality,
  formatQualitySummary,
  QUALITY_DIMENSIONS,
} from "./deepResearchQualityRubric";

describe("evaluateDeepResearchQuality", () => {
  it("computes weighted overall from known dimensions", () => {
    const r = evaluateDeepResearchQuality({
      research_id: "dr-1",
      dimensions: [
        { dimension: "citation_density", score: 0.8 },
        { dimension: "claim_grounding", score: 1.0 },
        { dimension: "intellectual_honesty", score: 0.9 },
      ],
    });
    expect(r.persisted).toBe(false);
    expect(r.known_count).toBe(3);
    expect(r.missing).toContain("source_diversity");
    expect(r.overall).not.toBeNull();
    expect(r.overall!).toBeGreaterThan(0.8);
    expect(r.authority).toBe("deep_research_quality_rubric_advisory");
  });

  it("overall null when no dimensions known", () => {
    const r = evaluateDeepResearchQuality({
      research_id: "dr-2",
      dimensions: [],
    });
    expect(r.overall).toBeNull();
    expect(r.known_count).toBe(0);
    expect(r.missing).toHaveLength(QUALITY_DIMENSIONS.length);
    expect(r.notes.some((n) => /no invent 0/.test(n))).toBe(true);
  });

  it("overall null when require_all and any missing", () => {
    const r = evaluateDeepResearchQuality({
      research_id: "dr-3",
      require_all_dimensions: true,
      dimensions: [{ dimension: "citation_density", score: 1 }],
    });
    expect(r.overall).toBeNull();
    expect(r.missing.length).toBeGreaterThan(0);
  });

  it("rejects out-of-range scores", () => {
    expect(() =>
      evaluateDeepResearchQuality({
        research_id: "dr",
        dimensions: [{ dimension: "actionability", score: 1.5 }],
      }),
    ).toThrow(/\[0, 1\]/);
  });

  it("rejects duplicate dimensions", () => {
    expect(() =>
      evaluateDeepResearchQuality({
        research_id: "dr",
        dimensions: [
          { dimension: "actionability", score: 0.5 },
          { dimension: "actionability", score: 0.6 },
        ],
      }),
    ).toThrow(/duplicate/);
  });

  it("rejects non-finite scores", () => {
    expect(() =>
      evaluateDeepResearchQuality({
        research_id: "dr",
        dimensions: [{ dimension: "actionability", score: Number.NaN }],
      }),
    ).toThrow(/finite/);
  });

  it("treats explicit null score as unknown", () => {
    const r = evaluateDeepResearchQuality({
      research_id: "dr",
      dimensions: [{ dimension: "citation_density", score: null }],
    });
    expect(r.known_count).toBe(0);
    expect(r.overall).toBeNull();
  });
});

describe("formatQualitySummary", () => {
  it("summarizes honesty", () => {
    const r = evaluateDeepResearchQuality({
      research_id: "dr-x",
      dimensions: [],
    });
    expect(formatQualitySummary(r)).toMatch(/overall=null/);
    expect(formatQualitySummary(r)).toMatch(/persisted=false/);
  });
});
