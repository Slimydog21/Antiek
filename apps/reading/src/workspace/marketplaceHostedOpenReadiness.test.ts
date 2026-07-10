import { describe, expect, it } from "vitest";
import { marketplaceHostedOpenReadiness } from "./marketplaceHostedOpenReadiness";

describe("marketplaceHostedOpenReadiness residual (atm)", () => {
  it("is not ready when fields empty", () => {
    const r = marketplaceHostedOpenReadiness({});
    expect(r.open_ready).toBe(false);
    expect(r.view_format_html).toBe(false);
    expect(r.has_html_body).toBe(false);
    expect(r.has_document_id).toBe(false);
    expect(r.never_pdf_view).toBe(true);
    expect(r.html_first).toBe(true);
    expect(r.summary).toMatch(/html/i);
  });

  it("rejects pdf view_format", () => {
    const r = marketplaceHostedOpenReadiness({
      view_format: "pdf",
      html: "<p>x</p>",
      document_id: "doc_1",
    });
    expect(r.view_format_html).toBe(false);
    expect(r.open_ready).toBe(false);
    expect(r.open_title).toMatch(/not a reading surface|html/i);
  });

  it("rejects empty body", () => {
    const r = marketplaceHostedOpenReadiness({
      view_format: "html",
      html: "   ",
      document_id: "doc_1",
    });
    expect(r.has_html_body).toBe(false);
    expect(r.open_ready).toBe(false);
    expect(r.summary).toMatch(/empty/i);
  });

  it("rejects missing document_id", () => {
    const r = marketplaceHostedOpenReadiness({
      view_format: "html",
      html: "<p>Hosted</p>",
      document_id: "",
    });
    expect(r.has_document_id).toBe(false);
    expect(r.open_ready).toBe(false);
    expect(r.open_title).toMatch(/document_id missing/i);
  });

  it("ready when html + body + document_id", () => {
    const r = marketplaceHostedOpenReadiness({
      view_format: "HTML",
      html: "<article><h1>Book</h1></article>",
      document_id: "hdoc_free_1",
    });
    expect(r.open_ready).toBe(true);
    expect(r.view_format_html).toBe(true);
    expect(r.has_html_body).toBe(true);
    expect(r.has_document_id).toBe(true);
    expect(r.view_format).toBe("html");
    expect(r.summary).toMatch(/ready/i);
    expect(r.open_title).toMatch(/never PDF/i);
  });
});
