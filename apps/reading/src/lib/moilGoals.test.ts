import { describe, expect, it } from "vitest";
import {
  appendMoilGoalTemplate,
  MOIL_GOAL_TEMPLATES,
  goalsExceedFanout,
  moilDepositHtmlReadiness,
  moilCeilingBudgetFit,
  moilPlanReadiness,
  parseMoilGoalLines,
  recommendedFanoutForGoals,
} from "./moilGoals";

describe("moilGoals (aof)", () => {
  it("parses one goal per non-empty line", () => {
    expect(parseMoilGoalLines("A\n\n  B  \nC")).toEqual(["A", "B", "C"]);
    expect(parseMoilGoalLines("")).toEqual([]);
    expect(parseMoilGoalLines(null)).toEqual([]);
  });

  it("appends templates without inventing duplicates", () => {
    const t = MOIL_GOAL_TEMPLATES[0].text;
    expect(appendMoilGoalTemplate("", t)).toBe(t);
    expect(appendMoilGoalTemplate("Existing", t)).toBe(`Existing\n${t}`);
    expect(appendMoilGoalTemplate(t, t)).toBe(t);
    expect(appendMoilGoalTemplate("x", "")).toBe("x");
  });

  it("ships a closed set of professional research templates", () => {
    expect(MOIL_GOAL_TEMPLATES.length).toBeGreaterThanOrEqual(3);
    for (const row of MOIL_GOAL_TEMPLATES) {
      expect(row.id).toBeTruthy();
      expect(row.label).toBeTruthy();
      expect(row.text.length).toBeGreaterThan(10);
    }
  });

  it("ships north-star workstation templates (ara)", () => {
    const ids = MOIL_GOAL_TEMPLATES.map((t) => t.id);
    expect(ids).toContain("knowledge_dense_refs");
    expect(ids).toContain("multi_agent_analysis");
    expect(ids).toContain("budget_wrestle");
    expect(ids).toContain("reading_merge");
    expect(MOIL_GOAL_TEMPLATES.length).toBeGreaterThanOrEqual(8);
  });

  it("recommends fan-out to cover goal count (aow)", () => {
    expect(recommendedFanoutForGoals(0)).toBe(1);
    expect(recommendedFanoutForGoals(4)).toBe(4);
    expect(recommendedFanoutForGoals(20)).toBe(12);
    expect(recommendedFanoutForGoals(20, 8)).toBe(8);
    expect(recommendedFanoutForGoals(-1)).toBe(1);
  });

  it("detects goals exceeding fan-out (aox)", () => {
    expect(goalsExceedFanout(0, 3)).toBe(false);
    expect(goalsExceedFanout(3, 3)).toBe(false);
    expect(goalsExceedFanout(4, 3)).toBe(true);
    expect(goalsExceedFanout(2, 0)).toBe(true);
  });

  it("computes plan readiness before ceiling (ara)", () => {
    expect(moilPlanReadiness({}).plan_ready).toBe(false);
    expect(moilPlanReadiness({ goalsText: "A" }).plan_ready).toBe(false);
    expect(
      moilPlanReadiness({ goalsText: "A\nB", durationMinutes: 30 }).plan_ready,
    ).toBe(true);
    const under = moilPlanReadiness({
      goalsText: "A\nB\nC\nD",
      durationMinutes: 60,
      fanoutDepth: 2,
    });
    expect(under.goal_count).toBe(4);
    expect(under.goals_exceed_fanout).toBe(true);
    expect(under.recommended_fanout).toBe(4);
    expect(under.summary).toMatch(/under-covers|recommend/i);
    const ready = moilPlanReadiness({
      goalsText: "A\nB",
      durationMinutes: 45,
      fanoutDepth: 2,
    });
    expect(ready.plan_ready).toBe(true);
    expect(ready.goals_exceed_fanout).toBe(false);
    expect(ready.summary).toMatch(/plan ready/i);
  });

  it("computes deposit HTML open readiness (ate)", () => {
    expect(moilDepositHtmlReadiness({}).deposit_html_ready).toBe(false);
    expect(
      moilDepositHtmlReadiness({ view_format: "pdf", html: "<p>x</p>" })
        .view_format_html,
    ).toBe(false);
    expect(
      moilDepositHtmlReadiness({
        view_format: "html",
        html: "   ",
        document_id: "doc_1",
      }).has_html_body,
    ).toBe(false);
    expect(
      moilDepositHtmlReadiness({
        view_format: "html",
        html: "<p>body</p>",
      }).has_document_id,
    ).toBe(false);
    const ready = moilDepositHtmlReadiness({
      view_format: "html",
      html: "<p>Deposited</p>",
      document_id: "draft_moil_1",
    });
    expect(ready.deposit_html_ready).toBe(true);
    expect(ready.summary).toMatch(/html deposit ready/i);
    expect(ready.open_title).toMatch(/never PDF/i);
    const noId = moilDepositHtmlReadiness({
      view_format: "html",
      html: "<p>x</p>",
      document_id: "",
    });
    expect(noId.deposit_html_ready).toBe(false);
    expect(noId.open_title).toMatch(/document_id missing/i);
  });

  it("computes ceiling vs remaining budget fit (auf)", () => {
    expect(moilCeilingBudgetFit({ ceiling_usd: 5 }).fit).toBe("unknown");
    expect(moilCeilingBudgetFit({ ceiling_usd: 5 }).may_exceed).toBe(false);
    expect(
      moilCeilingBudgetFit({ ceiling_usd: 3, remaining_usd: 10 }).fit,
    ).toBe("fits");
    expect(
      moilCeilingBudgetFit({ ceiling_usd: 3, remaining_usd: 10 }).may_exceed,
    ).toBe(false);
    expect(
      moilCeilingBudgetFit({ ceiling_usd: 3, remaining_usd: 10 })
        .remaining_after_usd,
    ).toBeCloseTo(7);
    const over = moilCeilingBudgetFit({
      ceiling_usd: 12,
      remaining_usd: 5,
    });
    expect(over.fit).toBe("may_exceed");
    expect(over.may_exceed).toBe(true);
    expect(over.remaining_after_usd).toBeCloseTo(-7);
    expect(over.soft_budget).toBe(true);
    expect(over.summary).toMatch(/may exceed/i);
  });
});
