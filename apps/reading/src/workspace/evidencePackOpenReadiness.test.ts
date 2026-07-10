import { describe, expect, it } from "vitest";
import { evidencePackOpenReadiness } from "./evidencePackOpenReadiness";

describe("evidencePackOpenReadiness (aua)", () => {
  it("is not open_ready when HTML empty", () => {
    const r = evidencePackOpenReadiness({});
    expect(r.open_ready).toBe(false);
    expect(r.write_ready).toBe(false);
    expect(r.citation_trust).toBe("ungrounded");
    expect(r.source).toBe("evidence_pack");
    expect(r.html_first).toBe(true);
    expect(r.never_pdf_view).toBe(true);
  });

  it("is open_ready grounded when HTML + refs", () => {
    const r = evidencePackOpenReadiness({
      html: "<section>Evidence pack</section>",
      ref_count: 2,
      has_insight_text: true,
    });
    expect(r.open_ready).toBe(true);
    expect(r.write_ready).toBe(true);
    expect(r.citation_trust).toBe("grounded");
    expect(r.ref_count).toBe(2);
    expect(r.summary).toMatch(/grounded/i);
    expect(r.open_title).toMatch(/never PDF/i);
  });

  it("is open_ready ungrounded when HTML without refs", () => {
    const r = evidencePackOpenReadiness({
      html: "<p>no sources</p>",
      ref_count: 0,
    });
    expect(r.open_ready).toBe(true);
    expect(r.citation_trust).toBe("ungrounded");
    expect(r.summary).toMatch(/ungrounded/i);
  });

  it("is write_ready from twin text alone without inventing HTML open", () => {
    const r = evidencePackOpenReadiness({
      has_insight_text: true,
      ref_count: 1,
    });
    expect(r.open_ready).toBe(false);
    expect(r.write_ready).toBe(true);
    expect(r.citation_trust).toBe("grounded");
  });
});
