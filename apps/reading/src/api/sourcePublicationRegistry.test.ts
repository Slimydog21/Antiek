import { describe, expect, it } from "vitest";
import {
  formatSourcePackSummary,
  selectPublicationSources,
} from "./sourcePublicationRegistry";

describe("selectPublicationSources", () => {
  it("selects arxiv and substack with fetched false", () => {
    const pack = selectPublicationSources({
      requested_families: ["arxiv", "substack"],
    });
    expect(pack.fetched).toBe(false);
    expect(pack.sources.map((s) => s.family).sort()).toEqual([
      "arxiv",
      "substack",
    ]);
    expect(pack.authority).toBe("source_publication_registry_advisory");
  });

  it("rejects empty requested families", () => {
    expect(() =>
      selectPublicationSources({ requested_families: [] }),
    ).toThrow(/non-empty/);
  });

  it("includes custom when requested", () => {
    const pack = selectPublicationSources({
      requested_families: ["custom"],
      custom_sources: [
        {
          source_id: "my-blog",
          family: "custom",
          label: "My Research Blog",
          enabled: true,
        },
      ],
    });
    expect(pack.sources).toHaveLength(1);
    expect(pack.sources[0].source_id).toBe("my-blog");
    expect(pack.fetched).toBe(false);
  });

  it("skips disabled customs when enabled_only", () => {
    const pack = selectPublicationSources({
      requested_families: ["custom"],
      custom_sources: [
        {
          source_id: "off",
          family: "custom",
          label: "Off",
          enabled: false,
        },
      ],
      enabled_only: true,
    });
    expect(pack.sources).toHaveLength(0);
  });

  it("rejects non-custom family in custom_sources", () => {
    expect(() =>
      selectPublicationSources({
        requested_families: ["arxiv"],
        custom_sources: [
          {
            source_id: "x",
            family: "arxiv",
            label: "x",
            enabled: true,
          },
        ],
      }),
    ).toThrow(/must be custom/);
  });
});

describe("formatSourcePackSummary", () => {
  it("summarizes honesty", () => {
    const pack = selectPublicationSources({
      requested_families: ["arxiv"],
    });
    expect(formatSourcePackSummary(pack)).toMatch(/fetched=false/);
  });
});
