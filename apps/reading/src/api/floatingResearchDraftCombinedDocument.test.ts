import { describe, expect, it } from "vitest";
import {
  composeFloatingResearchDraftCombinedDocument,
  formatFloatingDraftCombinedSummary,
} from "./floatingResearchDraftCombinedDocument";

describe("composeFloatingResearchDraftCombinedDocument", () => {
  it("builds provisional draft without writing", () => {
    const d = composeFloatingResearchDraftCombinedDocument({
      parent_asset_id: "asset-1",
      parent_excerpt: "<p>Original parent body</p>",
      operator_ack: false,
      sources: [
        {
          instance_id: "fdr_1",
          parent_asset_id: "asset-1",
          status: "completed",
          highlight: "scaling laws",
          findings: ["claim A holds under noise"],
        },
      ],
    });
    expect(d.draft_written).toBe(false);
    expect(d.merge_executed).toBe(false);
    expect(d.draft_ready).toBe(true);
    expect(d.section_count).toBeGreaterThanOrEqual(3);
    expect(d.sections.some((s) => s.includes("Original parent"))).toBe(true);
    expect(d.authority).toBe(
      "floating_research_draft_combined_document_advisory",
    );
    expect(formatFloatingDraftCombinedSummary(d)).toMatch(/draft_written=false/);
  });

  it("not ready without findings or highlight", () => {
    const d = composeFloatingResearchDraftCombinedDocument({
      parent_asset_id: "a",
      parent_excerpt: "body",
      operator_ack: true,
      sources: [
        {
          instance_id: "f1",
          parent_asset_id: "a",
          status: "open",
        },
      ],
    });
    expect(d.draft_ready).toBe(false);
    expect(d.draft_written).toBe(false);
    expect(d.merge_executed).toBe(false);
  });

  it("rejects cross-parent and closed sources", () => {
    expect(() =>
      composeFloatingResearchDraftCombinedDocument({
        parent_asset_id: "a",
        operator_ack: false,
        sources: [
          {
            instance_id: "f1",
            parent_asset_id: "other",
            status: "completed",
            findings: ["x"],
          },
        ],
      }),
    ).toThrow(/parent_asset_id/);
    expect(() =>
      composeFloatingResearchDraftCombinedDocument({
        parent_asset_id: "a",
        operator_ack: false,
        sources: [
          {
            instance_id: "f1",
            parent_asset_id: "a",
            status: "closed",
            findings: ["x"],
          },
        ],
      }),
    ).toThrow(/not closed/);
  });

  it("rejects empty sources and blank findings", () => {
    expect(() =>
      composeFloatingResearchDraftCombinedDocument({
        parent_asset_id: "a",
        operator_ack: false,
        sources: [],
      }),
    ).toThrow(/sources/);
    expect(() =>
      composeFloatingResearchDraftCombinedDocument({
        parent_asset_id: "a",
        operator_ack: false,
        sources: [
          {
            instance_id: "f1",
            parent_asset_id: "a",
            status: "completed",
            findings: ["  "],
          },
        ],
      }),
    ).toThrow(/findings/);
  });
});
