import { describe, expect, it } from "vitest";
import {
  composeSourcePublicationDrAttachQuality,
  formatSourcePublicationDrAttachQualitySummary,
} from "./sourcePublicationDrAttachQualityCompose";

describe("composeSourcePublicationDrAttachQuality", () => {
  it("arxiv+substack attach + citations + quality ready", () => {
    const c = composeSourcePublicationDrAttachQuality({
      session_id: "sess-1",
      parent_asset_id: "asset-1",
      requested_families: ["arxiv", "substack"],
      sources: [
        {
          source_id: "arx-1",
          family: "arxiv",
          title: "Scaling Laws for Neural Language Models",
          external_id: "arxiv:2001.08361",
          html_fragment: "<article>abstract…</article>",
        },
        {
          source_id: "sub-1",
          family: "substack",
          title: "The Batch essay",
          external_id: "substack:thebatch",
          url: "https://example.substack.com/p/x",
          html_fragment: "<article>essay…</article>",
        },
      ],
      quality_overall: 0.85,
      quality_floor: 0.7,
      would_exceed: false,
      operator_ack: true,
    });
    expect(c.attach.attach_ready).toBe(true);
    expect(c.citation_pack.pack_ready).toBe(true);
    expect(c.citation_pack.citation_count).toBe(2);
    expect(c.quality_gate.gate_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.remote_fetched).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.live_dispatch_authorized).toBe(false);
    expect(c.authority).toBe(
      "source_publication_dr_attach_quality_compose_advisory",
    );
    expect(formatSourcePublicationDrAttachQualitySummary(c)).toMatch(
      /pdf_view_authorized=false/,
    );
  });

  it("budget would_exceed blocks pack without override", () => {
    const c = composeSourcePublicationDrAttachQuality({
      session_id: "sess-2",
      parent_asset_id: "a",
      requested_families: ["arxiv"],
      sources: [
        {
          source_id: "arx-1",
          family: "arxiv",
          title: "Paper",
          html_fragment: "<p>x</p>",
        },
      ],
      quality_overall: 0.9,
      would_exceed: true,
      operator_ack: true,
    });
    expect(c.quality_gate.gate_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.live_dispatch_authorized).toBe(false);
  });

  it("low quality blocks pack", () => {
    const c = composeSourcePublicationDrAttachQuality({
      session_id: "sess-3",
      parent_asset_id: "a",
      requested_families: ["arxiv"],
      sources: [
        {
          source_id: "arx-1",
          family: "arxiv",
          title: "Paper",
          html_fragment: "<p>x</p>",
        },
      ],
      quality_overall: 0.2,
      quality_floor: 0.7,
      would_exceed: false,
      operator_ack: true,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.remote_fetched).toBe(false);
  });

  it("operator_ack false blocks pack", () => {
    const c = composeSourcePublicationDrAttachQuality({
      session_id: "sess-4",
      parent_asset_id: "a",
      requested_families: ["substack"],
      sources: [
        {
          source_id: "s1",
          family: "substack",
          title: "Essay",
          html_fragment: "<p>y</p>",
        },
      ],
      quality_overall: 0.9,
      would_exceed: false,
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.live_dispatch_authorized).toBe(false);
  });

  it("explicit citations preferred over derive", () => {
    const c = composeSourcePublicationDrAttachQuality({
      session_id: "sess-5",
      parent_asset_id: "a",
      requested_families: ["arxiv"],
      sources: [
        {
          source_id: "arx-1",
          family: "arxiv",
          title: "Paper A",
          html_fragment: "<p>a</p>",
        },
      ],
      citations: [
        {
          citation_id: "custom-1",
          family: "arxiv",
          title: "Custom citation title",
          external_id: "arxiv:9999.99999",
        },
      ],
      quality_overall: 0.8,
      would_exceed: false,
      operator_ack: true,
    });
    expect(c.citation_pack.citations[0].citation_id).toBe("custom-1");
    expect(c.pack_ready).toBe(true);
  });
});
