/**
 * CorpusSearch.test.tsx — Read SPR-08 M1.
 *
 * The Library search box over the owned corpus: a typed query returns ranked
 * owned docs; a dropped FILE biases results (file = query signal, NOT ingested);
 * the active-research THEME is folded in when present and degrades gracefully
 * when absent. We mock the corpusSearch client and assert WHAT query it received.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { CorpusSearchHit } from "../../api/corpusSearch";
import CorpusSearch from "./CorpusSearch";

const { corpusSearchMock } = vi.hoisted(() => ({ corpusSearchMock: vi.fn() }));

vi.mock("../../api/corpusSearch", async (orig) => {
  const actual = await orig<typeof import("../../api/corpusSearch")>();
  return { ...actual, corpusSearch: corpusSearchMock };
});

const hit = (over: Partial<CorpusSearchHit> = {}): CorpusSearchHit => ({
  chunk_id: "c1",
  document_id: "doc-1",
  document_title: "Quantum Book",
  page_index: 4,
  page_resolved: true,
  snippet: "a passage about quantum mechanics",
  similarity: 0.9,
  ...over,
});

beforeEach(() => {
  corpusSearchMock.mockReset();
});
afterEach(cleanup);

describe("CorpusSearch (M1)", () => {
  it("a typed query returns ranked owned docs", async () => {
    corpusSearchMock.mockResolvedValue({ query: "quantum", hits: [hit()], count: 1 });
    const onOpen = vi.fn();
    render(<CorpusSearch onOpen={onOpen} />);

    fireEvent.change(screen.getByLabelText("Search the corpus"), { target: { value: "quantum" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await screen.findByText("Quantum Book");
    expect(corpusSearchMock).toHaveBeenCalledWith("quantum");
    // The resolved-page result shows the page; clicking jumps there.
    fireEvent.click(screen.getByText("Quantum Book").closest("button")!);
    expect(onOpen).toHaveBeenCalledWith("doc-1", 4);
  });

  it("a dropped file biases the search (file = query SIGNAL, never ingested)", async () => {
    corpusSearchMock.mockResolvedValue({ query: "x", hits: [hit()], count: 1 });
    const onOpen = vi.fn();
    render(<CorpusSearch onOpen={onOpen} />);

    const section = screen.getByTestId("corpus-search");
    const file = new File(["a chapter about entanglement and superposition"], "notes.txt", {
      type: "text/plain",
    });
    // jsdom File.text() resolves; the component reads a bounded prefix as the query.
    fireEvent.drop(section, { dataTransfer: { files: [file] } });

    await waitFor(() => expect(corpusSearchMock).toHaveBeenCalled());
    const query = corpusSearchMock.mock.calls[0][0] as string;
    expect(query).toContain("entanglement");
    // The honest signal SAYS the file biased it.
    await screen.findByTestId("corpus-search-signal");
    expect(screen.getByTestId("corpus-search-signal").textContent).toContain("notes.txt");
  });

  it("folds theme-context into the query when present", async () => {
    corpusSearchMock.mockResolvedValue({ query: "free will", hits: [], count: 0 });
    render(<CorpusSearch onOpen={vi.fn()} themeContext={["determinism", "agency"]} />);

    fireEvent.change(screen.getByLabelText("Search the corpus"), { target: { value: "free will" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(corpusSearchMock).toHaveBeenCalled());
    const query = corpusSearchMock.mock.calls[0][0] as string;
    expect(query).toContain("free will");
    expect(query).toContain("determinism");
  });

  it("degrades gracefully with NO theme-context (raw query only)", async () => {
    corpusSearchMock.mockResolvedValue({ query: "stoicism", hits: [], count: 0 });
    render(<CorpusSearch onOpen={vi.fn()} themeContext={[]} />);

    fireEvent.change(screen.getByLabelText("Search the corpus"), { target: { value: "stoicism" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(corpusSearchMock).toHaveBeenCalled());
    expect(corpusSearchMock.mock.calls[0][0]).toBe("stoicism");
  });

  it("an unresolved-page hit opens the book without a fabricated page jump", async () => {
    corpusSearchMock.mockResolvedValue({
      query: "x",
      hits: [hit({ page_index: null, page_resolved: false })],
      count: 1,
    });
    const onOpen = vi.fn();
    render(<CorpusSearch onOpen={onOpen} />);
    fireEvent.change(screen.getByLabelText("Search the corpus"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByText("Quantum Book");
    expect(screen.getByText("open the book")).toBeTruthy();
    fireEvent.click(screen.getByText("Quantum Book").closest("button")!);
    // No page argument (null) — we never invent a page.
    expect(onOpen).toHaveBeenCalledWith("doc-1", null);
  });
});
