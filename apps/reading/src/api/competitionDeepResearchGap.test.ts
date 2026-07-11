import { describe, expect, it } from "vitest";
import {
  buildCompetitionDeepResearchGap,
  formatCompetitionGapSummary,
} from "./competitionDeepResearchGap";

describe("buildCompetitionDeepResearchGap", () => {
  it("counts statuses and collects residuals", () => {
    const m = buildCompetitionDeepResearchGap({
      decisions: [
        {
          competitor: "Perplexity",
          area: "source_acquisition",
          decision_summary: "Live web + citation cards",
          antiek_status: "parity",
        },
        {
          competitor: "Elicit",
          area: "citation_grounding",
          decision_summary: "Paper-grounded claims with spans",
          antiek_status: "behind",
          residual: "Wire citation spans into DR quality floor",
        },
        {
          competitor: "Consensus",
          area: "evaluation_harness",
          decision_summary: "Literature meta-analysis UX",
          antiek_status: "unknown",
        },
      ],
    });
    expect(m.backlog_mutated).toBe(false);
    expect(m.behind_count).toBe(1);
    expect(m.unknown_count).toBe(1);
    expect(m.parity_count).toBe(1);
    expect(m.residuals).toContain("Wire citation spans into DR quality floor");
    expect(m.authority).toBe("competition_deep_research_gap_advisory");
  });

  it("empty decisions yields empty matrix", () => {
    const m = buildCompetitionDeepResearchGap({ decisions: [] });
    expect(m.decisions).toEqual([]);
    expect(m.behind_count).toBe(0);
    expect(m.notes.some((n) => /no invent competitors/.test(n))).toBe(true);
  });

  it("focus_areas filters", () => {
    const m = buildCompetitionDeepResearchGap({
      focus_areas: ["budget_controls"],
      decisions: [
        {
          competitor: "A",
          area: "budget_controls",
          decision_summary: "Hard spend caps",
          antiek_status: "ahead",
        },
        {
          competitor: "B",
          area: "model_routing",
          decision_summary: "Auto router",
          antiek_status: "behind",
          residual: "should be filtered out",
        },
      ],
    });
    expect(m.decisions).toHaveLength(1);
    expect(m.behind_count).toBe(0);
    expect(m.ahead_count).toBe(1);
  });

  it("rejects blank competitor or summary", () => {
    expect(() =>
      buildCompetitionDeepResearchGap({
        decisions: [
          {
            competitor: "  ",
            area: "source_acquisition",
            decision_summary: "x",
            antiek_status: "parity",
          },
        ],
      }),
    ).toThrow(/competitor/);
  });

  it("rejects invalid status", () => {
    expect(() =>
      buildCompetitionDeepResearchGap({
        decisions: [
          {
            competitor: "X",
            area: "source_acquisition",
            decision_summary: "y",
            // @ts-expect-error intentional
            antiek_status: "winning",
          },
        ],
      }),
    ).toThrow(/antiek_status/);
  });
});

describe("formatCompetitionGapSummary", () => {
  it("summarizes honesty", () => {
    const m = buildCompetitionDeepResearchGap({ decisions: [] });
    expect(formatCompetitionGapSummary(m)).toMatch(/backlog_mutated=false/);
  });
});
