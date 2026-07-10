import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getHtmlProjectionByDocument } from "../../api/htmlProjections";
import { getChunk } from "../../lib/api";
import { openReader } from "../../workspace/actions";
import ChunkModal from "./ChunkModal";

vi.mock("../../api/htmlProjections", () => ({ getHtmlProjectionByDocument: vi.fn() }));
vi.mock("../../lib/api", () => ({ getChunk: vi.fn() }));
vi.mock("../../workspace/actions", () => ({ openReader: vi.fn() }));

const chunk = (section_path: string | null) => ({
  chunk_id: "chunk-1", text: "body", section_path, token_count: 3,
  document_id: "doc-1", document_title: "Source", source_tier: 1,
  servable: true, servability: null,
});
const projection = (mappings: Array<Record<string, unknown>>) => ({
  identity: {}, projection_id: "hproj", html_sha256: "hash", html: "", anchor_mappings: mappings,
});
const mapping = (id: string) => ({
  source_locator: { kind: "pdf_page_bbox", page: 7 }, state: "resolved" as const,
  html_anchor_id: id, candidates: [] as const,
});
const canonical = `antiek-anchor-${"a".repeat(64)}`;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function show(sectionPath: string | null) {
  vi.mocked(getChunk).mockResolvedValue(chunk(sectionPath));
  render(<ChunkModal chunkId="chunk-1" onClose={vi.fn()} />);
  return screen.findByRole("button", { name: /open (at page|in document)/i });
}

describe("ChunkModal canonical source navigation", () => {
  it("resolves a page and opens its canonical anchor", async () => {
    vi.mocked(getHtmlProjectionByDocument).mockResolvedValue(projection([mapping(canonical)]) as never);
    fireEvent.click(await show("Page 7"));
    await waitFor(() => expect(openReader).toHaveBeenCalledWith({
      documentId: "doc-1", anchorId: canonical, title: "Source",
    }));
    expect(vi.mocked(getHtmlProjectionByDocument).mock.calls[0][1]).toBeInstanceOf(AbortSignal);
  });

  it("opens the document root when there is no strict page locator", async () => {
    fireEvent.click(await show("Section 7"));
    expect(openReader).toHaveBeenCalledWith({ documentId: "doc-1", title: "Source" });
    expect(getHtmlProjectionByDocument).not.toHaveBeenCalled();
  });

  it("shows an accessible error and never guesses for an unresolved page", async () => {
    vi.mocked(getHtmlProjectionByDocument).mockResolvedValue(projection([]) as never);
    fireEvent.click(await show("Page 7"));
    expect((await screen.findByRole("alert")).textContent).toMatch(/no canonical location/i);
    expect(openReader).not.toHaveBeenCalled();
  });

  it("aborts an in-flight projection request when the chunk changes", async () => {
    vi.mocked(getHtmlProjectionByDocument).mockReturnValue(new Promise(() => {}));
    vi.mocked(getChunk).mockImplementation(async (id) => ({ ...chunk("Page 7"), chunk_id: id }));
    const view = render(<ChunkModal chunkId="chunk-1" onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: /open at page 7/i }));
    const signal = vi.mocked(getHtmlProjectionByDocument).mock.calls[0][1]!;
    view.rerender(<ChunkModal chunkId="chunk-2" onClose={vi.fn()} />);
    expect(signal.aborted).toBe(true);
  });
});
