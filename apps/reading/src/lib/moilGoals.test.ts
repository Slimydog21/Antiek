import { describe, expect, it } from "vitest";
import {
  appendMoilGoalTemplate,
  MOIL_GOAL_TEMPLATES,
  parseMoilGoalLines,
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
});
