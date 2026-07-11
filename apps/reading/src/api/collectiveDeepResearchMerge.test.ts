import { describe, expect, it } from "vitest";
import {
  formatCollectiveAnalysisSummary,
  proposeCollectiveAnalysisMerge,
} from "./collectiveDeepResearchMerge";

const base = [
  {
    instance_id: "fdr_1",
    parent_asset_id: "asset-1",
    status: "completed" as const,
    findings: ["claim A holds"],
  },
  {
    instance_id: "fdr_2",
    parent_asset_id: "asset-1",
    status: "completed" as const,
    findings: ["claim B needs counterexample"],
  },
];

describe("proposeCollectiveAnalysisMerge", () => {
  it("draft merge never writes analysis", () => {
    const intent = proposeCollectiveAnalysisMerge(base, {
      kind: "draft_analysis",
      operator_ack: false,
    });
    expect(intent.analysis_written).toBe(false);
    expect(intent.kind).toBe("draft_analysis");
    expect(intent.instance_ids).toHaveLength(2);
    expect(intent.findings).toHaveLength(2);
  });

  it("full analysis requires ack and completed", () => {
    expect(() =>
      proposeCollectiveAnalysisMerge(base, {
        kind: "full_analysis",
        operator_ack: false,
      }),
    ).toThrow(/operator_ack/);
    const open = [
      { ...base[0], status: "open" as const },
      { ...base[1] },
    ];
    expect(() =>
      proposeCollectiveAnalysisMerge(open, {
        kind: "full_analysis",
        operator_ack: true,
      }),
    ).toThrow(/completed/);
    const intent = proposeCollectiveAnalysisMerge(base, {
      kind: "full_analysis",
      operator_ack: true,
    });
    expect(intent.analysis_written).toBe(false);
    expect(intent.operator_ack).toBe(true);
  });

  it("requires ≥2 same parent", () => {
    expect(() =>
      proposeCollectiveAnalysisMerge([base[0]], {
        kind: "draft_analysis",
        operator_ack: false,
      }),
    ).toThrow(/at least 2/);
    expect(() =>
      proposeCollectiveAnalysisMerge(
        [base[0], { ...base[1], parent_asset_id: "other" }],
        { kind: "draft_analysis", operator_ack: false },
      ),
    ).toThrow(/same parent/);
  });

  it("never invents findings when none supplied", () => {
    const intent = proposeCollectiveAnalysisMerge(
      [
        {
          instance_id: "a",
          parent_asset_id: "p",
          status: "completed",
        },
        {
          instance_id: "b",
          parent_asset_id: "p",
          status: "completed",
        },
      ],
      { kind: "draft_analysis", operator_ack: false },
    );
    expect(intent.findings).toEqual([]);
    expect(intent.notes.some((n) => /no invent/.test(n))).toBe(true);
  });
});

describe("formatCollectiveAnalysisSummary", () => {
  it("summarizes honesty", () => {
    const intent = proposeCollectiveAnalysisMerge(base, {
      kind: "draft_analysis",
      operator_ack: false,
    });
    expect(formatCollectiveAnalysisSummary(intent)).toMatch(
      /analysis_written=false/,
    );
  });
});
