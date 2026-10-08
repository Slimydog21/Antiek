import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { API_BASE } from "../../lib/api";
import CorpusSearch from "./CorpusSearch";

const fetchMock = vi.fn<typeof fetch>();

function failure(status: number, detail = "embedding_unavailable") {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function pendingResponse() {
  let resolve: (response: Response) => void = () => {
    throw new Error("Unassigned transport response");
  };
  const promise = new Promise<Response>((accept) => { resolve = accept; });
  return { promise, resolve };
}

function submit(query: string) {
  fireEvent.change(screen.getByRole("searchbox", { name: "Search the corpus" }), {
    target: { value: query },
  });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
}

function expectNoResults() {
  expect(screen.queryByRole("list", { name: "Search results" })).toBeNull();
  expect(screen.queryByText(/Nothing in your corpus matched/)).toBeNull();
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Corpus search HTTP failures through the real client (synthetic UNIT responses only)", () => {
  it("shows the embedding 503 honestly and retries the same encoded credentialed GET", async () => {
    fetchMock.mockImplementation(async () => failure(503));
    const onOpen = vi.fn();
    const view = render(<CorpusSearch onOpen={onOpen} themeContext={["ethics", "politics", "learning", "voice", "excluded"]} />);

    submit("  choice & λόγος / agency  ");
    expect((await screen.findByRole("alert")).textContent).toContain("Search is temporarily unavailable.");
    expect(screen.queryByText("embedding_unavailable")).toBeNull();
    expectNoResults();

    view.rerender(<CorpusSearch onOpen={onOpen} themeContext={["a later context"]} />);
    fireEvent.click(screen.getByRole("button", { name: "Retry search" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Search is temporarily unavailable.");

    const query = "choice & λόγος / agency\n\n(in the context of: ethics, politics, learning, voice)";
    const url = `${API_BASE}/corpus/search?${new URLSearchParams({ q: query })}`;
    expect(fetchMock.mock.calls).toEqual([
      [url, expect.objectContaining({ credentials: "include" })],
      [url, expect.objectContaining({ credentials: "include" })],
    ]);
    for (const [, init] of fetchMock.mock.calls) {
      expect(init?.method ?? "GET").toBe("GET");
      expect(init?.body).toBeUndefined();
    }
    expect(onOpen).not.toHaveBeenCalled();
    expectNoResults();
  });

  it.each([401, 403])("preserves HTTP %i refusal instead of reporting an empty corpus", async (status) => {
    fetchMock.mockImplementation(async () => failure(status, "operator_auth_required"));
    const onOpen = vi.fn();
    render(<CorpusSearch onOpen={onOpen} />);

    submit("owned query");

    expect((await screen.findByRole("alert")).textContent).toContain(`GET /corpus/search: HTTP ${status}`);
    expect(screen.queryByText("Search is temporarily unavailable.")).toBeNull();
    expect(screen.getByRole("button", { name: "Retry search" })).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(onOpen).not.toHaveBeenCalled();
    expectNoResults();
  });

  it("keeps a network rejection recoverable without manufacturing results", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const onOpen = vi.fn();
    render(<CorpusSearch onOpen={onOpen} />);

    submit("network query");
    expect((await screen.findByRole("alert")).textContent).toContain("Failed to fetch");
    fireEvent.click(screen.getByRole("button", { name: "Retry search" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Failed to fetch");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1]).toEqual(fetchMock.mock.calls[0]);
    expect(onOpen).not.toHaveBeenCalled();
    expectNoResults();
  });

  it("a late 503 cannot replace a newer in-flight request or its current 403", async () => {
    const old = pendingResponse();
    const current = pendingResponse();
    fetchMock.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    const onOpen = vi.fn();
    render(<CorpusSearch onOpen={onOpen} />);

    submit("old query");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    submit("current query");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await act(async () => { old.resolve(failure(503)); });

    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: "Searching…" }).getAttribute("disabled")).not.toBeNull();
    expectNoResults();

    await act(async () => { current.resolve(failure(403, "owner_scope_required")); });

    expect(screen.getByRole("alert").textContent).toContain("GET /corpus/search: HTTP 403");
    expect(screen.queryByText("Search is temporarily unavailable.")).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(onOpen).not.toHaveBeenCalled();
    expectNoResults();
  });
});
