import { describe, expect, it } from "vitest";
import {
  buildDeepResearchSourceCitationPack,
  formatDeepResearchSourceCitationPackSummary,
} from "./deepResearchSourceCitationPack";

describe("buildDeepResearchSourceCitationPack", () => {
  it("builds pack without remote fetch", () => {
    const p = buildDeepResearchSourceCitationPack({
      session_id: "sess-1",
      requested_families: ["arxiv", "substack"],
      citations: [
        {
          citation_id: "c1",
          family: "arxiv",
          title: "Attention Is All You Need",
          external_id: "arxiv:1706.03762",
          url: "https://arxiv.org/abs/1706.03762",
          year: 2017,
          authors: "Vaswani et al.",
        },
        {
          citation_id: "c2",
          family: "substack",
          title: "Scaling notes",
          url: "https://example.substack.com/p/scaling",
        },
      ],
    });
    expect(p.remote_fetched).toBe(false);
    expect(p.selection.fetched).toBe(false);
    expect(p.pack_ready).toBe(true);
    expect(p.citation_count).toBe(2);
    expect(p.families_present).toContain("arxiv");
    expect(p.authority).toBe("deep_research_source_citation_pack_advisory");
    expect(formatDeepResearchSourceCitationPackSummary(p)).toMatch(
      /remote_fetched=false/,
    );
  });

  it("filters citations outside selected families", () => {
    const p = buildDeepResearchSourceCitationPack({
      session_id: "s",
      requested_families: ["arxiv"],
      filter_to_selected_families: true,
      citations: [
        {
          citation_id: "c1",
          family: "arxiv",
          title: "Paper A",
        },
        {
          citation_id: "c2",
          family: "web",
          title: "Blog B",
        },
      ],
    });
    expect(p.citation_count).toBe(1);
    expect(p.citations[0].citation_id).toBe("c1");
    expect(p.remote_fetched).toBe(false);
  });

  it("empty citations not pack_ready", () => {
    const p = buildDeepResearchSourceCitationPack({
      session_id: "s",
      requested_families: ["arxiv"],
      citations: [],
    });
    expect(p.pack_ready).toBe(false);
    expect(p.remote_fetched).toBe(false);
    expect(p.notes.some((n) => n.includes("no invent"))).toBe(true);
  });

  it("rejects duplicate ids and invalid url shape", () => {
    expect(() =>
      buildDeepResearchSourceCitationPack({
        session_id: "s",
        requested_families: ["arxiv"],
        citations: [
          { citation_id: "x", family: "arxiv", title: "A" },
          { citation_id: "x", family: "arxiv", title: "B" },
        ],
      }),
    ).toThrow(/duplicate/);
    expect(() =>
      buildDeepResearchSourceCitationPack({
        session_id: "s",
        requested_families: ["web"],
        citations: [
          {
            citation_id: "c1",
            family: "web",
            title: "T",
            url: "not-a-url",
          },
        ],
      }),
    ).toThrow(/url/);
  });

  it("rejects blank title", () => {
    expect(() =>
      buildDeepResearchSourceCitationPack({
        session_id: "s",
        requested_families: ["arxiv"],
        citations: [
          { citation_id: "c1", family: "arxiv", title: "  " },
        ],
      }),
    ).toThrow(/title/);
  });
});
