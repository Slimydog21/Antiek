import { describe, expect, it } from "vitest";
import { publicationHydrateOpenReadiness } from "./publicationHydrateOpenReadiness";

describe("publicationHydrateOpenReadiness (aty)", () => {
  it("is not open_ready when HTML empty", () => {
    const r = publicationHydrateOpenReadiness({});
    expect(r.open_ready).toBe(false);
    expect(r.write_ready).toBe(false);
    expect(r.offline_honest).toBe(true);
    expect(r.fetched).toBe(false);
    expect(r.source).toBe("publication_hydrate");
    expect(r.html_first).toBe(true);
    expect(r.never_pdf_view).toBe(true);
  });

  it("is open_ready offline-honest when HTML + identity + not fetched", () => {
    const r = publicationHydrateOpenReadiness({
      html: "<article>Attention Is All You Need</article>",
      asset_id: "pub_arxiv_abc",
      fetched: false,
    });
    expect(r.open_ready).toBe(true);
    expect(r.write_ready).toBe(true);
    expect(r.offline_honest).toBe(true);
    expect(r.has_document_id).toBe(true);
    expect(r.summary).toMatch(/offline-honest/i);
    expect(r.open_title).toMatch(/never PDF/i);
  });

  it("is open_ready injector path when fetched", () => {
    const r = publicationHydrateOpenReadiness({
      html: "<p>live body</p>",
      asset_id: "pub_1",
      fetched: true,
    });
    expect(r.open_ready).toBe(true);
    expect(r.offline_honest).toBe(false);
    expect(r.fetched).toBe(true);
    expect(r.summary).toMatch(/injector/i);
  });

  it("is write_ready from body_text alone without inventing HTML open", () => {
    const r = publicationHydrateOpenReadiness({
      body_text: "abstract only",
      asset_id: "pub_1",
      fetched: false,
    });
    expect(r.open_ready).toBe(false);
    expect(r.write_ready).toBe(true);
    expect(r.offline_honest).toBe(true);
  });
});
