import { describe, expect, it } from "vitest";
import {
  formatBenchRewriteSummary,
  proposeAntiekBenchRecursiveRewrite,
} from "./antiekBenchRecursiveRewrite";

describe("proposeAntiekBenchRecursiveRewrite", () => {
  it("proposes from failures with applied false", () => {
    const p = proposeAntiekBenchRecursiveRewrite({
      week_label: "2026-W28",
      patterns: [
        {
          task_family: "citation_binding",
          model_id: "model-a",
          outcome: "failed",
          n: 3,
        },
        {
          task_family: "citation_binding",
          model_id: "model-b",
          outcome: "worked",
          n: 2,
        },
        {
          task_family: "html_compose",
          model_id: "model-a",
          outcome: "mixed",
          n: 2,
        },
      ],
    });
    expect(p.applied).toBe(false);
    expect(p.proposals.length).toBe(2);
    expect(p.proposals[0].task_family).toBe("citation_binding");
    expect(p.proposals[0].priority).toBe(3);
    expect(p.proposals[0].focus_models[0]).toBe("model-a");
    expect(p.authority).toBe("antiek_bench_rewrite_advisory");
  });

  it("empty patterns yields empty proposals", () => {
    const p = proposeAntiekBenchRecursiveRewrite({
      week_label: "2026-W28",
      patterns: [],
    });
    expect(p.proposals).toEqual([]);
    expect(p.applied).toBe(false);
  });

  it("unknown outcome does not invent failure weight", () => {
    const p = proposeAntiekBenchRecursiveRewrite({
      week_label: "2026-W28",
      patterns: [
        {
          task_family: "research_pack",
          model_id: "m1",
          outcome: "unknown",
          n: 10,
        },
      ],
    });
    expect(p.proposals).toEqual([]);
    expect(p.notes.some((n) => /unknown/.test(n))).toBe(true);
  });

  it("rejects bad outcome and non-positive n", () => {
    expect(() =>
      proposeAntiekBenchRecursiveRewrite({
        week_label: "w",
        patterns: [
          // @ts-expect-error intentional
          { task_family: "t", model_id: "m", outcome: "great" },
        ],
      }),
    ).toThrow(/outcome/);
    expect(() =>
      proposeAntiekBenchRecursiveRewrite({
        week_label: "w",
        patterns: [
          {
            task_family: "t",
            model_id: "m",
            outcome: "failed",
            n: 0,
          },
        ],
      }),
    ).toThrow(/n/);
  });

  it("requires week_label", () => {
    expect(() =>
      proposeAntiekBenchRecursiveRewrite({
        week_label: "  ",
        patterns: [],
      }),
    ).toThrow(/week_label/);
  });
});

describe("formatBenchRewriteSummary", () => {
  it("summarizes applied false", () => {
    const p = proposeAntiekBenchRecursiveRewrite({
      week_label: "2026-W28",
      patterns: [],
    });
    expect(formatBenchRewriteSummary(p)).toMatch(/applied=false/);
  });
});
