/**
 * ReadingColumn.test.tsx — Read SPR-09 M3 acceptance, including the BINDING
 * SPR-07 prerequisite closure.
 *
 * Load-bearing claims (each ASSERTED, not eyeballed):
 *  - a servable column renders the served body as prose (headings + paragraphs);
 *  - it carries `data-akb-asset-id={documentId}` so the SPR-07 sampler can see
 *    it — and we PROVE the closure by driving the REAL `useFrameAttention`
 *    against a rendered column and asserting it emits a sample for that asset
 *    (not a hand-rolled DOM, the actual component);
 *  - a gated column (assetId null) renders the body BUT carries NO asset marker
 *    — the sampler must not attribute a preview snippet (§9.0);
 *  - a chunk marker is added only when a real chunk id is present (never an
 *    empty/fabricated attribute).
 *
 * jsdom has no layout, so geometry for the sampler is stamped via a
 * getBoundingClientRect stub — the same approach useFrameAttention.test.ts uses.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, renderHook, screen } from "@testing-library/react";

import { useFrameAttention, type FrameAttentionResult } from "../ad/useFrameAttention";
import ReadingColumn from "./ReadingColumn";

const VW = 1000;
const VH = 800;

function stampFullViewport(el: Element): void {
  el.getBoundingClientRect = () =>
    ({
      left: 0,
      top: 0,
      right: VW,
      bottom: VH,
      width: VW,
      height: VH,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    }) as DOMRect;
}

afterEach(() => {
  cleanup();
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("ReadingColumn — rendering", () => {
  it("renders the served body as headings and paragraphs", () => {
    render(<ReadingColumn assetId="doc-1" text={"# Chapter One\n\nFirst paragraph.\n\nSecond paragraph."} />);
    expect(screen.getByRole("heading", { name: "Chapter One" })).toBeTruthy();
    expect(screen.getByText("First paragraph.")).toBeTruthy();
    expect(screen.getByText("Second paragraph.")).toBeTruthy();
  });

  it("shows an honest empty-body note when there is no text", () => {
    render(<ReadingColumn assetId="doc-1" text="" />);
    expect(screen.getByText(/no readable pages/i)).toBeTruthy();
  });
});

describe("ReadingColumn — SPR-07 attribution markers (§9.0)", () => {
  it("tags a servable column with data-akb-asset-id = the document id", () => {
    const { container } = render(<ReadingColumn assetId="doc-42" text="Body." />);
    const article = container.querySelector("article")!;
    expect(article.getAttribute("data-akb-asset-id")).toBe("doc-42");
  });

  it("does NOT tag a gated column (assetId null) — no preview attribution", () => {
    const { container } = render(<ReadingColumn assetId={null} text="Snippet." />);
    const article = container.querySelector("article")!;
    expect(article.hasAttribute("data-akb-asset-id")).toBe(false);
    // body still renders (it's a gate-served snippet), just unattributed.
    expect(screen.getByText("Snippet.")).toBeTruthy();
  });

  it("tags each authoritative chunk region without attributing the whole article", () => {
    const { container: withChunk } = render(
      <ReadingColumn
        assetId="doc-1"
        text="Body."
        chunks={[
          { chunk_id: "chunk-7", chunk_index: 0, page_index: 0, text: "First." },
          { chunk_id: "chunk-8", chunk_index: 1, page_index: 0, text: "Second." },
        ]}
      />,
    );
    expect(withChunk.querySelector("article")!.hasAttribute("data-akb-chunk-id")).toBe(false);
    expect(
      [...withChunk.querySelectorAll("[data-akb-chunk-id]")].map((node) =>
        node.getAttribute("data-akb-chunk-id"),
      ),
    ).toEqual(["chunk-7", "chunk-8"]);

    cleanup();
    const { container: noChunk } = render(<ReadingColumn assetId="doc-1" text="Body." />);
    expect(noChunk.querySelector("article")!.hasAttribute("data-akb-chunk-id")).toBe(false);
  });
});

describe("ReadingColumn — closes the SPR-07 attribution prereq end-to-end", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.defineProperty(window, "innerWidth", { value: VW, configurable: true });
    Object.defineProperty(window, "innerHeight", { value: VH, configurable: true });
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    document.hasFocus = () => true;
  });
  afterEach(() => vi.useRealTimers());

  it("the REAL useFrameAttention detects a rendered servable column as an in-frame asset", () => {
    // Render the actual component into the document (the sampler falls back to
    // document.body as the working region when no shell frame is present).
    render(<ReadingColumn assetId="doc-99" text="A servable body the sampler should see." />);
    const article = document.querySelector('article[data-akb-asset-id="doc-99"]')!;
    expect(article).toBeTruthy();
    stampFullViewport(article);

    const seconds: FrameAttentionResult[] = [];
    renderHook(() =>
      useFrameAttention({ lens: "read", onSecond: (r) => seconds.push(r) }),
    );
    vi.advanceTimersByTime(1000);

    expect(seconds).toHaveLength(1);
    const sample = seconds[0]!.second.samples.find((s) => s.asset_id === "doc-99");
    expect(sample).toBeDefined();
    expect(sample!.viewport_area_fraction).toBeGreaterThan(0);
    expect(seconds[0]!.unresolved).toBe(0);
  });

  it("a gated (untagged) column produces NO sample — a house second, not preview attribution", () => {
    render(<ReadingColumn assetId={null} text="A gated preview snippet." />);
    // No element carries the asset marker → nothing for the sampler to find.
    expect(document.querySelector("[data-akb-asset-id]")).toBeNull();

    const seconds: FrameAttentionResult[] = [];
    renderHook(() =>
      useFrameAttention({ lens: "read", onSecond: (r) => seconds.push(r) }),
    );
    vi.advanceTimersByTime(1000);

    expect(seconds).toHaveLength(1);
    expect(seconds[0]!.second.samples).toHaveLength(0);
  });
});
