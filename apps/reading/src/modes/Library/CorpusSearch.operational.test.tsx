import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CorpusSearchResponse } from "../../api/corpusSearch";
import CorpusSearch from "./CorpusSearch";

const { searchMock } = vi.hoisted(() => ({ searchMock: vi.fn() }));
vi.mock("../../api/corpusSearch", () => ({ corpusSearch: searchMock }));

function pendingSearch() {
  let reject: (error: Error) => void = () => { throw new Error("unassigned request"); };
  const promise = new Promise<CorpusSearchResponse>((_, fail) => { reject = fail; });
  return { promise, reject };
}
function typeQuery(query: string) {
  fireEvent.change(screen.getByRole("searchbox", { name: "Search the corpus" }), { target: { value: query } });
}
function submit() { fireEvent.click(screen.getByRole("button", { name: "Search" })); }

beforeEach(() => { searchMock.mockReset(); });
afterEach(cleanup);

describe("Corpus search operational recovery (synthetic failures only)", () => {
  it("retries the exact failed themed query without claiming no matches", async () => {
    searchMock.mockRejectedValue(new Error("Search is temporarily unavailable."));
    render(<CorpusSearch onOpen={vi.fn()} themeContext={["agency"]} />);
    typeQuery("free will"); submit();
    await screen.findByRole("alert");
    expect(screen.queryByText(/Nothing in your corpus matched/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry search" }));
    expect(searchMock.mock.calls).toEqual([
      ["free will\n\n(in the context of: agency)"],
      ["free will\n\n(in the context of: agency)"],
    ]);
    await screen.findByRole("alert");
  });

  it("an older failure/finally cannot change the newer in-flight search", async () => {
    const old = pendingSearch(); const current = pendingSearch();
    searchMock.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    render(<CorpusSearch onOpen={vi.fn()} />);
    typeQuery("old"); submit();
    typeQuery("current"); submit();
    expect(searchMock.mock.calls).toEqual([["old"], ["current"]]);
    await act(async () => { old.reject(new Error("obsolete failure")); });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: "Searching…" }).getAttribute("disabled")).not.toBeNull();
    await act(async () => { current.reject(new Error("current failure")); });
    expect(screen.getByRole("alert").textContent).toContain("current failure");
  });

  it("clear retires a pending search and its late failure", async () => {
    const request = pendingSearch(); searchMock.mockReturnValue(request.promise);
    render(<CorpusSearch onOpen={vi.fn()} />);
    typeQuery("pending"); submit();
    fireEvent.click(screen.getByRole("button", { name: "clear search" }));
    await act(async () => { request.reject(new Error("cleared failure")); });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("searchbox").getAttribute("value")).toBe("");
    expect(screen.getByRole("button", { name: "Search" }).getAttribute("disabled")).toBeNull();
    expect(screen.queryByText(/Nothing in your corpus matched/)).toBeNull();
  });

  it("editing during file read prevents that file from starting a stale search", async () => {
    let resolveText: (text: string) => void = () => { throw new Error("unassigned file read"); };
    const text = new Promise<string>((resolve) => { resolveText = resolve; });
    const file = new File(["query signal"], "query.txt", { type: "text/plain" });
    Object.defineProperty(file, "text", { value: () => text });
    render(<CorpusSearch onOpen={vi.fn()} />);
    fireEvent.drop(screen.getByTestId("corpus-search"), { dataTransfer: { files: [file] } });
    typeQuery("new draft");
    await act(async () => { resolveText("old file signal"); });
    expect(searchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("searchbox").getAttribute("value")).toBe("new draft");
    expect(screen.getByRole("button", { name: "Search" }).getAttribute("disabled")).toBeNull();
  });

  it("unmount during file read prevents post-unmount search dispatch", async () => {
    let resolveText: (text: string) => void = () => { throw new Error("unassigned file read"); };
    const text = new Promise<string>((resolve) => { resolveText = resolve; });
    const file = new File(["query signal"], "query.txt");
    Object.defineProperty(file, "text", { value: () => text });
    const view = render(<CorpusSearch onOpen={vi.fn()} />);
    fireEvent.drop(screen.getByTestId("corpus-search"), { dataTransfer: { files: [file] } });
    view.unmount();
    await act(async () => { resolveText("retired file signal"); });
    expect(searchMock).not.toHaveBeenCalled();
  });
});
