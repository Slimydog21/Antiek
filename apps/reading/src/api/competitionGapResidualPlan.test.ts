import { describe, expect, it } from "vitest";
import {
  buildCompetitionGapResidualPlan,
  formatCompetitionGapResidualPlanSummary,
} from "./competitionGapResidualPlan";
import type { CompetitorDecision } from "./competitionDeepResearchGap";

const decisions: CompetitorDecision[] = [
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
  {
    competitor: "X",
    area: "model_routing",
    decision_summary: "Auto router",
    antiek_status: "behind",
  },
];

describe("buildCompetitionGapResidualPlan", () => {
  it("orders behind before unknown and never mutates backlog", () => {
    const plan = buildCompetitionGapResidualPlan({ decisions });
    expect(plan.backlog_mutated).toBe(false);
    expect(plan.item_count).toBe(3);
    expect(plan.p0_count).toBe(2);
    expect(plan.unknown_planned).toBe(1);
    expect(plan.items[0].priority).toBe("P0");
    expect(plan.items[0].residual_text).toMatch(/citation spans/);
    expect(plan.items[1].priority).toBe("P0");
    expect(plan.items[1].residual_text).toMatch(/without residual text/);
    expect(plan.items[2].priority).toBe("P1");
    expect(plan.authority).toBe("competition_gap_residual_plan_advisory");
    expect(formatCompetitionGapResidualPlanSummary(plan)).toMatch(
      /backlog_mutated=false/,
    );
  });

  it("empty when only ahead/parity", () => {
    const plan = buildCompetitionGapResidualPlan({
      decisions: [
        {
          competitor: "A",
          area: "budget_controls",
          decision_summary: "caps",
          antiek_status: "ahead",
        },
      ],
    });
    expect(plan.items).toEqual([]);
    expect(plan.notes.some((n) => n.includes("no invent items"))).toBe(true);
    expect(plan.backlog_mutated).toBe(false);
  });

  it("respects max_items", () => {
    const plan = buildCompetitionGapResidualPlan({
      decisions,
      max_items: 1,
    });
    expect(plan.item_count).toBe(1);
    expect(plan.items[0].antiek_status).toBe("behind");
    expect(plan.notes.some((n) => n.includes("max_items=1"))).toBe(true);
  });

  it("rejects invalid max_items and blank competitor", () => {
    expect(() =>
      buildCompetitionGapResidualPlan({ decisions, max_items: 0 }),
    ).toThrow(/max_items/);
    expect(() =>
      buildCompetitionGapResidualPlan({
        decisions: [
          {
            competitor: "  ",
            area: "source_acquisition",
            decision_summary: "x",
            antiek_status: "behind",
          },
        ],
      }),
    ).toThrow(/competitor/);
  });

  it("includes execution_hint without inventing competitors", () => {
    const plan = buildCompetitionGapResidualPlan({
      decisions: [
        {
          competitor: "Elicit",
          area: "citation_grounding",
          decision_summary: "spans",
          antiek_status: "behind",
          residual: "Wire spans",
        },
      ],
    });
    expect(plan.items[0].execution_hint).toMatch(/citation/);
    expect(plan.items[0].competitor).toBe("Elicit");
    expect(plan.backlog_mutated).toBe(false);
  });
});
