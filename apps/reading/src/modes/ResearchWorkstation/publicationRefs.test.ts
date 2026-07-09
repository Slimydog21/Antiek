import { describe, expect, it, vi, beforeEach } from "vitest";

import {
  hydratePublicationRefs,
  parsePublicationRefs,
  questionWithPublicationRefs,
} from "./publicationRefs";

const hydratePublicationRef = vi.fn();

vi.mock("../../api/engagement", () => ({
  hydratePublicationRef: (...args: unknown[]) => hydratePublicationRef(...args),
}));

describe("publicationRefs residual cj", () => {
  beforeEach(() => {
    hydratePublicationRef.mockReset();
  });

  it("parses one ref per non-empty line", () => {
    expect(
      parsePublicationRefs("arxiv:1706.03762\n\n  substack:https://x.substack.com/p/y  \n"),
    ).toEqual(["arxiv:1706.03762", "substack:https://x.substack.com/p/y"]);
  });

  it("appends references block to question", () => {
    const q = questionWithPublicationRefs("What is attention?", [
      "arxiv:1706.03762",
    ]);
    expect(q).toMatch(/What is attention\?/);
    expect(q).toMatch(/Publication references/);
    expect(q).toMatch(/arxiv:1706\.03762/);
  });

  it("hydrates refs offline and rejects non-html", async () => {
    hydratePublicationRef
      .mockResolvedValueOnce({
        asset_id: "pub_arxiv_1",
        ref: { kind: "arxiv", raw: "arxiv:1706.03762" },
        title: "Attention",
        body_text: "…",
        fetched: false,
        view_format: "html",
        notes: [],
        product_panel: "engagement_hydrate",
        source: "test",
        html: "<p>Attention</p>",
      })
      .mockResolvedValueOnce({
        asset_id: "bad",
        ref: { kind: "url", raw: "https://x.test" },
        title: "x",
        body_text: "",
        fetched: false,
        view_format: "pdf",
        notes: [],
        product_panel: "engagement_hydrate",
        source: "test",
      });

    const out = await hydratePublicationRefs([
      "arxiv:1706.03762",
      "https://x.test",
    ]);
    expect(out.view_format).toBe("html");
    expect(out.ok).toHaveLength(1);
    expect(out.ok[0].asset_id).toBe("pub_arxiv_1");
    expect(out.failed).toHaveLength(1);
    expect(out.failed[0].error).toMatch(/html/i);
  });
});
