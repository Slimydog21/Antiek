import { describe, expect, it } from "vitest";

import {
  prepareHtmlDraftForWrite,
  stripHtmlToPlainText,
  titleHintFromDraft,
} from "./htmlDraftImport";

describe("htmlDraftImport residual fm", () => {
  it("strips tags and scripts to plain text", () => {
    const plain = stripHtmlToPlainText(
      "<p>Hello <b>world</b></p><script>alert(1)</script><style>.x{}</style>",
    );
    expect(plain).toBe("Hello world");
  });

  it("titleHint prefers API title then plain text then document id", () => {
    expect(
      titleHintFromDraft({ title: "  Merged research  ", plain_text: "ignored" }),
    ).toBe("Merged research");
    expect(
      titleHintFromDraft({
        title: "",
        plain_text: "First sentence. Second.",
        document_id: "d1",
      }),
    ).toBe("First sentence.");
    expect(titleHintFromDraft({ document_id: "draft_abc" })).toMatch(/draft_abc/);
  });

  it("prepareHtmlDraftForWrite requires html view_format and body", () => {
    expect(() =>
      prepareHtmlDraftForWrite({
        document_id: "d1",
        view_format: "pdf",
        html: "%PDF",
      }),
    ).toThrow(/html/i);
    expect(() =>
      prepareHtmlDraftForWrite({
        document_id: "d1",
        view_format: "html",
        html: "   ",
      }),
    ).toThrow(/empty/i);
    const out = prepareHtmlDraftForWrite({
      document_id: "draft_1",
      view_format: "html",
      title: "Analysis",
      html: "<article><h1>Hi</h1><p>Body text here.</p></article>",
    });
    expect(out.view_format).toBe("html");
    expect(out.title).toBe("Analysis");
    expect(out.plain_text).toMatch(/Body text here/);
    expect(out.plain_preview.length).toBeGreaterThan(5);
  });
});
