import { describe, expect, it } from "vitest";
import { highlightDrLaunchReadiness } from "./highlightDrLaunchReadiness";

describe("highlightDrLaunchReadiness residual (asq)", () => {
  it("is not ready without document", () => {
    const r = highlightDrLaunchReadiness({});
    expect(r.launch_ready).toBe(false);
    expect(r.document_bound).toBe(false);
    expect(r.html_ready).toBe(true);
    expect(r.has_highlight).toBe(false);
    expect(r.summary).toMatch(/bind document/i);
  });

  it("requires HTML view_format", () => {
    const pdf = highlightDrLaunchReadiness({
      documentId: "doc-1",
      viewFormat: "pdf",
      highlightText: "sel",
    });
    expect(pdf.launch_ready).toBe(false);
    expect(pdf.html_ready).toBe(false);
    expect(pdf.view_format).toBe("other");
    expect(pdf.summary).toMatch(/html/i);
  });

  it("is launch ready for HTML document with or without highlight", () => {
    const page = highlightDrLaunchReadiness({
      documentId: "doc-1",
      viewFormat: "html",
    });
    expect(page.launch_ready).toBe(true);
    expect(page.has_highlight).toBe(false);
    expect(page.summary).toMatch(/book\/page-level/i);

    const hi = highlightDrLaunchReadiness({
      documentId: "doc-1",
      highlightText: "  Attention is routing.  ",
    });
    expect(hi.launch_ready).toBe(true);
    expect(hi.has_highlight).toBe(true);
    expect(hi.summary).toMatch(/highlight selection/i);
  });
});
