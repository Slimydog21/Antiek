import { describe, expect, it } from "vitest";
import { contextSearchOpenReadiness } from "./contextSearchOpenReadiness";

describe("contextSearchOpenReadiness (aty)", () => {
  it("is not open_ready when HTML empty", () => {
    const r = contextSearchOpenReadiness({});
    expect(r.open_ready).toBe(false);
    expect(r.write_ready).toBe(false);
    expect(r.html_first).toBe(true);
    expect(r.never_pdf_view).toBe(true);
    expect(r.source).toBe("context_search");
    expect(r.view_format).toBe("html");
  });

  it("is open_ready when HTML body present", () => {
    const r = contextSearchOpenReadiness({
      html: "<p>Query: attention · hits=1</p>",
      query: "attention",
      hit_count: 1,
      has_hit_text: true,
    });
    expect(r.open_ready).toBe(true);
    expect(r.write_ready).toBe(true);
    expect(r.has_html_body).toBe(true);
    expect(r.has_query).toBe(true);
    expect(r.hit_count).toBe(1);
    expect(r.summary).toMatch(/HTML ready/i);
    expect(r.open_title).toMatch(/never PDF/i);
  });

  it("is write_ready from hit text alone without inventing HTML open", () => {
    const r = contextSearchOpenReadiness({
      html: "  ",
      has_hit_text: true,
      hit_count: 2,
    });
    expect(r.open_ready).toBe(false);
    expect(r.write_ready).toBe(true);
    expect(r.summary).toMatch(/Write ready/i);
  });
});
