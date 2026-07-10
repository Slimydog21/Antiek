import { describe, expect, it } from "vitest";
import { researchContextPackOpenReadiness } from "./researchContextPackOpenReadiness";

describe("researchContextPackOpenReadiness (aub)", () => {
  it("is not open_ready when prompt_block empty", () => {
    const r = researchContextPackOpenReadiness({});
    expect(r.open_ready).toBe(false);
    expect(r.write_ready).toBe(false);
    expect(r.source).toBe("research_context_pack");
    expect(r.html_first).toBe(true);
    expect(r.never_pdf_view).toBe(true);
  });

  it("is open_ready when prompt_block present", () => {
    const r = researchContextPackOpenReadiness({
      prompt_block: "## Context\n- twin insight",
      twin_count: 2,
      ref_count: 1,
    });
    expect(r.open_ready).toBe(true);
    expect(r.write_ready).toBe(true);
    expect(r.has_prompt_body).toBe(true);
    expect(r.twin_count).toBe(2);
    expect(r.ref_count).toBe(1);
    expect(r.summary).toMatch(/ready/i);
    expect(r.open_title).toMatch(/never PDF/i);
  });

  it("treats whitespace-only prompt as empty", () => {
    const r = researchContextPackOpenReadiness({ prompt_block: "  \n  " });
    expect(r.open_ready).toBe(false);
    expect(r.write_ready).toBe(false);
  });
});
