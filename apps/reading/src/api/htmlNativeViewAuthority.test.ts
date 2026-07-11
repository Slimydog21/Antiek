import { describe, expect, it } from "vitest";
import {
  evaluateHtmlNativeViewAuthority,
  formatHtmlViewSummary,
} from "./htmlNativeViewAuthority";

describe("evaluateHtmlNativeViewAuthority", () => {
  it("authorizes HTML when projection sha present", () => {
    const d = evaluateHtmlNativeViewAuthority({
      asset_id: "book-1",
      asset_kind: "book",
      source_format: "pdf",
      html_projection_sha: "sha256:abc123ready",
    });
    expect(d.human_viewable_html).toBe(true);
    expect(d.primary_format).toBe("html");
    expect(d.pdf_secondary_allowed).toBe(true);
    expect(d.authority).toBe("html_native_view_authority_advisory");
  });

  it("does not invent ready HTML without sha", () => {
    const d = evaluateHtmlNativeViewAuthority({
      asset_id: "paper-1",
      asset_kind: "paper",
      source_format: "pdf",
      html_projection_sha: null,
    });
    expect(d.human_viewable_html).toBe(false);
    expect(d.primary_format).toBe("unavailable");
    expect(d.html_projection_sha).toBeNull();
  });

  it("blank sha is not ready", () => {
    const d = evaluateHtmlNativeViewAuthority({
      asset_id: "r-1",
      asset_kind: "research",
      source_format: "html",
      html_projection_sha: "   ",
    });
    expect(d.human_viewable_html).toBe(false);
  });

  it("prefer_html false denies human html", () => {
    const d = evaluateHtmlNativeViewAuthority({
      asset_id: "a",
      asset_kind: "twin",
      source_format: "html",
      html_projection_sha: "sha:1",
      prefer_html: false,
    });
    expect(d.human_viewable_html).toBe(false);
  });

  it("rejects bad kind", () => {
    expect(() =>
      evaluateHtmlNativeViewAuthority({
        asset_id: "a",
        // @ts-expect-error intentional
        asset_kind: "video",
        source_format: "html",
      }),
    ).toThrow(/asset_kind/);
  });
});

describe("formatHtmlViewSummary", () => {
  it("summarizes", () => {
    const d = evaluateHtmlNativeViewAuthority({
      asset_id: "a",
      asset_kind: "book",
      source_format: "pdf",
      html_projection_sha: "sha:ready",
    });
    expect(formatHtmlViewSummary(d)).toMatch(/human_viewable_html=true/);
  });
});
