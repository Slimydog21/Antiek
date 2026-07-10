import { describe, expect, it } from "vitest";
import { spawnMergeHtmlOpenReadiness } from "./spawnMergeHtmlOpenReadiness";

describe("spawnMergeHtmlOpenReadiness (aup)", () => {
  it("is not open_ready when fields missing", () => {
    expect(spawnMergeHtmlOpenReadiness({}).open_ready).toBe(false);
    expect(
      spawnMergeHtmlOpenReadiness({
        view_format: "pdf",
        html: "<p>x</p>",
        document_id: "d1",
      }).open_ready,
    ).toBe(false);
    expect(
      spawnMergeHtmlOpenReadiness({
        view_format: "html",
        html: "  ",
        document_id: "d1",
      }).has_html_body,
    ).toBe(false);
  });

  it("is open_ready for draft_combined HTML product", () => {
    const r = spawnMergeHtmlOpenReadiness({
      view_format: "html",
      html: "<article>Merged</article>",
      document_id: "merge_abc",
      mode: "draft_combined",
    });
    expect(r.open_ready).toBe(true);
    expect(r.source).toBe("spawn_merge");
    expect(r.merge_mode).toBe("draft_combined");
    expect(r.html_first).toBe(true);
    expect(r.never_pdf_view).toBe(true);
    expect(r.open_title).toMatch(/never PDF/i);
  });
});
