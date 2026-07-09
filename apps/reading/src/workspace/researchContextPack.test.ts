import { describe, expect, it } from "vitest";
import {
  assertHtmlViewFormat,
  detectSourceKindClient,
  formatCollectivePromptBlock,
  formatResearchContextPromptBlock,
  type CollectiveResearchUnit,
  type ResearchContextPack,
} from "./researchContextPack";

const samplePack: ResearchContextPack = {
  asset_id: "paper-attention",
  spawn_id: "spn_abc",
  investigation_id: "inv_abc",
  view_format: "html",
  twin_units: [
    {
      unit_id: "ins_1",
      twin_note_id: "twin_1",
      kind: "insight",
      text: "Self-attention parallelizes token conditioning.",
      canonical_text: "self-attention parallelizes token conditioning.",
      asset_id: "paper-attention",
      investigation_id: "inv_abc",
    },
  ],
  source_references: [
    {
      ref_id: "sref_1",
      kind: "arxiv",
      raw: "https://arxiv.org/abs/1706.03762",
      canonical_url: "https://arxiv.org/abs/1706.03762",
      external_id: "1706.03762",
    },
  ],
};

describe("researchContextPack", () => {
  it("formats prompt block with twins and arxiv refs", () => {
    const block = formatResearchContextPromptBlock(samplePack);
    expect(block).toContain("paper-attention");
    expect(block).toContain("Self-attention");
    expect(block).toContain("1706.03762");
    expect(block).toContain("[arxiv]");
  });

  it("formats research_tier in prompt block when present (kk/kl)", () => {
    const block = formatResearchContextPromptBlock({
      ...samplePack,
      research_tier: "wrestle",
    });
    expect(block).toContain("research_tier: wrestle");
    expect(block).toContain("spawn: spn_abc");
  });

  it("formats collective prompt block", () => {
    const unit: CollectiveResearchUnit = {
      collective_id: "col_xyz",
      spawn_ids: ["spn_a", "spn_b"],
      asset_ids: ["a", "b"],
      investigation_ids: ["inv_a"],
      view_format: "html",
      twin_units: samplePack.twin_units,
      source_references: samplePack.source_references,
    };
    const block = formatCollectivePromptBlock(unit);
    expect(block).toContain("col_xyz");
    expect(block).toContain("spn_a");
    expect(block).toContain("Self-attention");
  });

  it("detects arxiv and substack kinds client-side", () => {
    expect(detectSourceKindClient("https://arxiv.org/abs/2402.03300")).toBe("arxiv");
    expect(detectSourceKindClient("2402.03300")).toBe("arxiv");
    expect(detectSourceKindClient("https://foo.substack.com/p/hello")).toBe("substack");
    expect(detectSourceKindClient("https://example.com/x")).toBe("url");
  });

  it("asserts html view format", () => {
    expect(() => assertHtmlViewFormat({ view_format: "html" })).not.toThrow();
    expect(() => assertHtmlViewFormat({ view_format: "pdf" })).toThrow(/html/);
  });
});
