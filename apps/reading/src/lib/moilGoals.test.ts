import { describe, expect, it } from "vitest";
import {
  appendMoilGoalTemplate,
  MOIL_GOAL_TEMPLATES,
  goalsExceedFanout,
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
});
