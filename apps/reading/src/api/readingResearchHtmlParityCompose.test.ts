import { describe, expect, it } from "vitest";
import {
  composeReadingResearchHtmlParity,
  formatReadingResearchHtmlParitySummary,
} from "./readingResearchHtmlParityCompose";

describe("composeReadingResearchHtmlParity", () => {
  it("parity ready when both HTML with same sha", () => {
    const c = composeReadingResearchHtmlParity({
      reading: {
        asset_id: "a1",
        asset_kind: "book",
        source_format: "epub",
        html_projection_sha: "sha-abc",
      },
      research: {
        asset_id: "a1",
        asset_kind: "research",
        source_format: "markdown",
        html_projection_sha: "sha-abc",
      },
    });
    expect(c.pdf_primary).toBe(false);
    expect(c.both_html_ready).toBe(true);
    expect(c.primary_format_aligned).toBe(true);
    expect(c.parity_ready).toBe(true);
    expect(c.authority).toBe("reading_research_html_parity_compose_advisory");
    expect(formatReadingResearchHtmlParitySummary(c)).toMatch(/pdf_primary=false/);
  });

  it("parity false when sha differs", () => {
    const c = composeReadingResearchHtmlParity({
      reading: {
        asset_id: "a1",
        asset_kind: "book",
        source_format: "html",
        html_projection_sha: "sha-1",
      },
      research: {
        asset_id: "a1",
        asset_kind: "research",
        source_format: "html",
        html_projection_sha: "sha-2",
      },
    });
    expect(c.both_html_ready).toBe(true);
    expect(c.parity_ready).toBe(false);
    expect(c.pdf_primary).toBe(false);
  });

  it("never invents sha when missing", () => {
    const c = composeReadingResearchHtmlParity({
      reading: {
        asset_id: "a1",
        asset_kind: "paper",
        source_format: "pdf",
        html_projection_sha: null,
      },
      research: {
        asset_id: "a1",
        asset_kind: "research",
        source_format: "pdf",
        html_projection_sha: null,
      },
    });
    expect(c.both_html_ready).toBe(false);
    expect(c.parity_ready).toBe(false);
    expect(c.pdf_primary).toBe(false);
    expect(c.reading.primary_format).toBe("unavailable");
    expect(c.research.primary_format).toBe("unavailable");
    expect(c.notes.some((n) => n.includes("no invent"))).toBe(true);
  });

  it("rejects missing mode inputs", () => {
    expect(() =>
      composeReadingResearchHtmlParity({
        reading: null as unknown as never,
        research: {
          asset_id: "a",
          asset_kind: "research",
          source_format: "html",
          html_projection_sha: "x",
        },
      }),
    ).toThrow(/reading/);
  });
});
