import { describe, expect, it } from "vitest";
import {
  composeHtmlNativeSourceAttach,
  formatHtmlNativeSourceAttachSummary,
} from "./htmlNativeSourceAttachCompose";

describe("composeHtmlNativeSourceAttach", () => {
  it("attaches arxiv/substack without remote fetch or PDF authority", () => {
    const c = composeHtmlNativeSourceAttach({
      session_id: "ws-1",
      parent_asset_id: "asset-1",
      requested_families: ["arxiv", "substack"],
      operator_ack: true,
      sources: [
        {
          source_id: "s1",
          family: "arxiv",
          title: "Scaling laws",
          external_id: "arxiv:2301.00001",
          html_fragment: "<article>abstract…</article>",
        },
        {
          source_id: "s2",
          family: "substack",
          title: "Essay on routing",
          url: "https://example.substack.com/p/routing",
        },
      ],
    });
    expect(c.attach_ready).toBe(true);
    expect(c.source_count).toBe(2);
    expect(c.html_ready_count).toBe(1);
    expect(c.remote_fetched).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.authority).toBe("html_native_source_attach_compose_advisory");
    expect(formatHtmlNativeSourceAttachSummary(c)).toMatch(
      /remote_fetched=false/,
    );
  });

  it("not ready without ack or sources", () => {
    const noAck = composeHtmlNativeSourceAttach({
      session_id: "ws-1",
      parent_asset_id: "a",
      requested_families: ["arxiv"],
      operator_ack: false,
      sources: [
        {
          source_id: "s1",
          family: "arxiv",
          title: "T",
          html_fragment: "<p>x</p>",
        },
      ],
    });
    expect(noAck.attach_ready).toBe(false);
    expect(noAck.remote_fetched).toBe(false);

    const empty = composeHtmlNativeSourceAttach({
      session_id: "ws-1",
      parent_asset_id: "a",
      requested_families: ["arxiv"],
      operator_ack: true,
      sources: [],
    });
    expect(empty.attach_ready).toBe(false);
  });

  it("rejects family not requested and duplicates", () => {
    expect(() =>
      composeHtmlNativeSourceAttach({
        session_id: "ws",
        parent_asset_id: "a",
        requested_families: ["arxiv"],
        operator_ack: true,
        sources: [
          {
            source_id: "s1",
            family: "substack",
            title: "T",
          },
        ],
      }),
    ).toThrow(/not in requested_families/);
    expect(() =>
      composeHtmlNativeSourceAttach({
        session_id: "ws",
        parent_asset_id: "a",
        requested_families: ["arxiv"],
        operator_ack: true,
        sources: [
          { source_id: "s1", family: "arxiv", title: "A" },
          { source_id: "s1", family: "arxiv", title: "B" },
        ],
      }),
    ).toThrow(/duplicate/);
  });
});
