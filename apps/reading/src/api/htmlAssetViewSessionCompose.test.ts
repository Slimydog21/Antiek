import { describe, expect, it } from "vitest";
import {
  composeHtmlAssetViewSession,
  formatHtmlAssetViewSessionSummary,
} from "./htmlAssetViewSessionCompose";

describe("composeHtmlAssetViewSession", () => {
  it("opens HTML session without PDF authority", () => {
    const c = composeHtmlAssetViewSession({
      session_id: "vs-1",
      asset_id: "asset-1",
      html_projection_sha: "sha-html-1",
      view_requested: true,
      twin_bound: true,
      twin_substrate_ready: true,
    });
    expect(c.session_ready).toBe(true);
    expect(c.html_view_ready).toBe(true);
    expect(c.twin_ready).toBe(true);
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(formatHtmlAssetViewSessionSummary(c)).toMatch(
      /pdf_view_authorized=false/,
    );
  });

  it("denies PDF claim and missing projection", () => {
    const pdf = composeHtmlAssetViewSession({
      session_id: "vs",
      asset_id: "a",
      html_projection_sha: "sha",
      view_requested: true,
      twin_bound: false,
      claimed_format: "pdf",
    });
    expect(pdf.html_view_ready).toBe(false);
    expect(pdf.session_ready).toBe(false);
    expect(pdf.pdf_view_authorized).toBe(false);

    const missing = composeHtmlAssetViewSession({
      session_id: "vs",
      asset_id: "a",
      html_projection_sha: null,
      view_requested: true,
      twin_bound: false,
    });
    expect(missing.session_ready).toBe(false);
    expect(missing.pdf_view_authorized).toBe(false);
  });
});
