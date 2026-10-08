import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";

import type { CorpusSearchHit } from "../../api/corpusSearch";
import * as owner from "../../lib/accountWorkspaceOwner";
import CorpusSearch from "./CorpusSearch";

function deferred<T>() {
  let resolve: (value: T) => void = () => { throw new Error("unassigned UNIT resolver"); };
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

const fetchMock = vi.fn<typeof fetch>();
const disposers: Array<() => void> = [];
const unavailable = () => new Response("synthetic UNIT unavailable", { status: 503 });
const unitTitle = "UNIT search result";
const unitHit: CorpusSearchHit = {
  chunk_id: "unit-search-chunk",
  document_id: "unit-search-document",
  document_title: unitTitle,
  page_index: 4,
  page_resolved: true,
  snippet: "Synthetic component fixture, never a real catalogue or book.",
  similarity: 0.9,
};
const unitResult = () => new Response(JSON.stringify({
  query: "unit query", hits: [unitHit], count: 1,
}), { status: 200, headers: { "Content-Type": "application/json" } });

function typeQuery(query: string) {
  fireEvent.change(screen.getByRole("searchbox", { name: "Search the corpus" }), { target: { value: query } });
}
function submit() { fireEvent.click(screen.getByRole("button", { name: "Search" })); }
function drop(file: File) {
  fireEvent.drop(screen.getByTestId("corpus-search"), { dataTransfer: { files: [file] } });
}
function queries() {
  return fetchMock.mock.calls.map(([input]) => {
    const url = input instanceof Request ? input.url : String(input);
    return new URL(url, "https://unit.invalid").searchParams.get("q");
  });
}
function replaceOwner(aba: boolean) {
  owner.setWorkspaceOwner("unit-search-b");
  if (aba) owner.setWorkspaceOwner("unit-search-a");
}
function lastConfirmation(spy: MockInstance<typeof owner.awaitWorkspaceOwnerSession>) {
  const result = spy.mock.results.at(-1);
  if (!result || result.type !== "return") throw new Error("UNIT confirmation was not returned");
  return result.value;
}
function observe(listener: Parameters<typeof owner.subscribeWorkspaceOwnerAdmission>[0]) {
  const dispose = owner.subscribeWorkspaceOwnerAdmission(listener);
  disposers.push(dispose);
  return dispose;
}

beforeEach(() => {
  owner.setWorkspaceOwner("unit-search-a");
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(unavailable());
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  for (const dispose of disposers.splice(0)) dispose();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// Only fetch is substituted. Admission, confirmation and HTTP503 handling are
// the actual producer/client; these are synthetic UNIT controls, not live proof.
describe("Corpus search captured-account isolation (UNIT)", () => {
  it("holds a bounded file and exact themed Retry through same-token confirmation", async () => {
    const captured = owner.workspaceOwnerSession();
    const read = deferred<string>();
    const file = new File(["x".repeat(10000)], "unit-query.txt");
    const whole = vi.spyOn(file, "text").mockRejectedValue(new Error("unbounded UNIT read"));
    const nativeSlice = file.slice.bind(file);
    const slice = vi.spyOn(file, "slice").mockImplementation((start, end, type) => {
      const prefix = nativeSlice(start, end, type);
      Object.defineProperty(prefix, "text", { value: () => read.promise });
      return prefix;
    });
    const view = render(<CorpusSearch onOpen={vi.fn()} themeContext={["agency"]} />);
    drop(file);
    act(() => { owner.suspendWorkspaceOwner(); });
    await act(async () => { read.resolve("x".repeat(8192)); });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(slice).toHaveBeenCalledWith(0, 8192);
    expect(whole).not.toHaveBeenCalled();
    expect(owner.workspaceOwnerSession()).toBe(captured);
    const disposeBeforeDispatch = observe((snapshot) => {
      if (snapshot.state === "ready") expect(fetchMock).not.toHaveBeenCalled();
    });
    act(() => { expect(owner.resumeWorkspaceOwner(captured)).toBe(true); });
    expect((await screen.findByRole("alert")).textContent).toContain("temporarily unavailable");
    disposeBeforeDispatch();
    const exactQuery = `${"x".repeat(2000)}\n\n(in the context of: agency)`;
    expect(queries()).toEqual([exactQuery]);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: "include" });
    expect(fetchMock.mock.calls[0][1]?.body).toBeUndefined();
    view.rerender(<CorpusSearch onOpen={vi.fn()} themeContext={["different theme"]} />);
    act(() => { owner.suspendWorkspaceOwner(); });
    fireEvent.click(screen.getByRole("button", { name: "Retry search" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    act(() => { expect(owner.resumeWorkspaceOwner(captured)).toBe(true); });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(queries()).toEqual([exactQuery, exactQuery]);
    expect((await screen.findByRole("alert")).textContent).toContain("temporarily unavailable");
    expect(screen.queryByText(/Nothing in your corpus matched/)).toBeNull();
  });

  it.each([false, true])("refuses a pending file after A-to-B replacement (ABA=%s)", async (aba) => {
    const captured = owner.workspaceOwnerSession();
    const read = deferred<string>();
    const file = new File(["unit private signal"], "unit-query.txt");
    Object.defineProperty(file, "text", { value: () => read.promise });
    render(<CorpusSearch onOpen={vi.fn()} />);
    drop(file);
    act(() => { replaceOwner(aba); });
    expect(owner.workspaceOwnerSession()).not.toBe(captured);
    await act(async () => { read.resolve("unit private signal"); });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("searchbox").getAttribute("value")).toBe("");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it.each(["edit", "clear", "unmount", "replace"] as const)(
    "aborts the actual suspended confirmation resource on %s",
    async (operation) => {
      const captured = owner.workspaceOwnerSession();
      const confirmation = vi.spyOn(owner, "awaitWorkspaceOwnerSession");
      const view = render(<CorpusSearch onOpen={vi.fn()} />);
      typeQuery("unit private query");
      act(() => { owner.suspendWorkspaceOwner(); });
      submit();
      expect(confirmation).toHaveBeenCalledWith(captured, expect.any(AbortSignal));
      const signal = confirmation.mock.calls[0]?.[1];
      if (!signal) throw new Error("UNIT confirmation must own a signal");
      expect(signal.aborted).toBe(false);
      if (operation === "edit") typeQuery("new draft");
      if (operation === "clear") fireEvent.click(screen.getByRole("button", { name: "clear search" }));
      if (operation === "unmount") view.unmount();
      if (operation === "replace") act(() => { owner.setWorkspaceOwner("unit-search-b"); });
      expect(signal.aborted).toBe(true);
      await act(async () => { owner.resumeWorkspaceOwner(captured); });
      expect(fetchMock).not.toHaveBeenCalled();
      if (operation === "edit") expect(screen.getByRole("searchbox").getAttribute("value")).toBe("new draft");
    },
  );

  it.each([false, true])("does not renew a suspended typed query onto a replacement (ABA=%s)", async (aba) => {
    const captured = owner.workspaceOwnerSession();
    render(<CorpusSearch onOpen={vi.fn()} />);
    typeQuery("unit private query");
    act(() => { owner.suspendWorkspaceOwner(); });
    submit();
    act(() => { replaceOwner(aba); });
    await act(async () => { expect(owner.resumeWorkspaceOwner(captured)).toBe(false); });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("searchbox").getAttribute("value")).toBe("");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it.each([false, true])("checks the captured token again after ready confirmation (ABA=%s)", async (aba) => {
    const confirmation = vi.spyOn(owner, "awaitWorkspaceOwnerSession");
    render(<CorpusSearch onOpen={vi.fn()} />);
    typeQuery("unit private query"); submit();
    const pending = lastConfirmation(confirmation);
    await act(async () => { replaceOwner(aba); await pending; });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("searchbox").getAttribute("value")).toBe("");
  });

  it.each([false, true])("does not resend a retained Retry onto a replacement (ABA=%s)", async (aba) => {
    const confirmation = vi.spyOn(owner, "awaitWorkspaceOwnerSession");
    render(<CorpusSearch onOpen={vi.fn()} />);
    typeQuery("unit original query"); submit();
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Retry search" }));
    const pending = lastConfirmation(confirmation);
    await act(async () => { replaceOwner(aba); await pending; });
    expect(queries()).toEqual(["unit original query"]);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("searchbox").getAttribute("value")).toBe("");
  });

  it("never dispatches inside a ready observer before a later observer fails", async () => {
    const captured = owner.workspaceOwnerSession();
    render(<CorpusSearch onOpen={vi.fn()} />);
    typeQuery("unit private query");
    act(() => { owner.suspendWorkspaceOwner(); });
    observe((snapshot) => {
      if (snapshot.state === "ready") {
        submit();
        expect(fetchMock).not.toHaveBeenCalled();
      }
    });
    const failure = new Error("synthetic later ready observer failure");
    observe((snapshot) => { if (snapshot.state === "ready") throw failure; });
    await act(async () => { expect(() => owner.resumeWorkspaceOwner(captured)).toThrow(failure); });
    expect(owner.workspaceOwnerAdmission().state).toBe("failed");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("searchbox").getAttribute("value")).toBe("");
  });

  it("holds an actual HTTP503 completion during same-A suspension", async () => {
    const response = deferred<Response>();
    fetchMock.mockReturnValueOnce(response.promise);
    const captured = owner.workspaceOwnerSession();
    render(<CorpusSearch onOpen={vi.fn()} />);
    typeQuery("unit pending query"); submit();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    act(() => { owner.suspendWorkspaceOwner(); });
    await act(async () => { response.resolve(unavailable()); });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: "Searching…" }).getAttribute("disabled")).not.toBeNull();
    act(() => { expect(owner.resumeWorkspaceOwner(captured)).toBe(true); });
    expect((await screen.findByRole("alert")).textContent).toContain("temporarily unavailable");
    expect(queries()).toEqual(["unit pending query"]);
  });

  it("an old account's HTTP503 cannot overwrite a new account's busy state or draft", async () => {
    const old = deferred<Response>();
    const current = deferred<Response>();
    fetchMock.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    render(<CorpusSearch onOpen={vi.fn()} />);
    typeQuery("unit old query"); submit();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    act(() => { owner.setWorkspaceOwner("unit-search-b"); });
    typeQuery("unit current query"); submit();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await act(async () => { old.resolve(unavailable()); });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("searchbox").getAttribute("value")).toBe("unit current query");
    expect(screen.getByRole("button", { name: "Searching…" }).getAttribute("disabled")).not.toBeNull();
    await act(async () => { current.resolve(unavailable()); });
    expect((await screen.findByRole("alert")).textContent).toContain("temporarily unavailable");
    expect(queries()).toEqual(["unit old query", "unit current query"]);
  });

  it.each([false, true])("refuses a late UNIT result and opening after replacement (ABA=%s)", async (aba) => {
    const response = deferred<Response>();
    fetchMock.mockReturnValueOnce(response.promise);
    const onOpen = vi.fn();
    render(<CorpusSearch onOpen={onOpen} />);
    typeQuery("unit private query"); submit();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    act(() => { replaceOwner(aba); });
    await act(async () => { response.resolve(unitResult()); });
    expect(screen.queryByText(unitTitle)).toBeNull();
    expect(screen.queryByRole("list", { name: "Search results" })).toBeNull();
    expect(screen.getByRole("searchbox").getAttribute("value")).toBe("");
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("adopts and opens a permitted UNIT hit only after same-token confirmation", async () => {
    const response = deferred<Response>();
    fetchMock.mockReturnValueOnce(response.promise);
    const captured = owner.workspaceOwnerSession();
    const onOpen = vi.fn();
    render(<CorpusSearch onOpen={onOpen} />);
    typeQuery("unit query"); submit();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    act(() => { owner.suspendWorkspaceOwner(); });
    await act(async () => { response.resolve(unitResult()); });
    expect(screen.queryByText(unitTitle)).toBeNull();
    act(() => { expect(owner.resumeWorkspaceOwner(captured)).toBe(true); });
    await screen.findByText(unitTitle);
    fireEvent.click(screen.getByRole("button", { name: /UNIT search result/ }));
    await waitFor(() => expect(onOpen).toHaveBeenCalledWith(unitHit.document_id, 4));
    expect(owner.workspaceOwnerSession()).toBe(captured);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("refuses opening if the captured hit's owner retires before the confirmation continuation", async () => {
    fetchMock.mockResolvedValueOnce(unitResult());
    const onOpen = vi.fn();
    const confirmation = vi.spyOn(owner, "awaitWorkspaceOwnerSession");
    render(<CorpusSearch onOpen={onOpen} />);
    typeQuery("unit query"); submit();
    await screen.findByText(unitTitle);
    fireEvent.click(screen.getByRole("button", { name: /UNIT search result/ }));
    const pending = lastConfirmation(confirmation);
    await act(async () => { owner.setWorkspaceOwner("unit-search-b"); await pending; });
    expect(onOpen).not.toHaveBeenCalled();
    expect(screen.queryByText(unitTitle)).toBeNull();
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("disposes each actual resource admission subscription and confirmation on unmount", async () => {
    const originalSubscribe = owner.subscribeWorkspaceOwnerAdmission;
    const subscriptions: Array<ReturnType<typeof vi.fn<() => void>>> = [];
    vi.spyOn(owner, "subscribeWorkspaceOwnerAdmission").mockImplementation((listener) => {
      const dispose = originalSubscribe(listener);
      const unsubscribe = vi.fn(dispose);
      subscriptions.push(unsubscribe);
      return unsubscribe;
    });
    const confirmation = vi.spyOn(owner, "awaitWorkspaceOwnerSession");
    const view = render(<CorpusSearch onOpen={vi.fn()} />);
    typeQuery("unit query");
    act(() => { owner.suspendWorkspaceOwner(); });
    submit();
    const signal = confirmation.mock.calls[0]?.[1];
    if (!signal) throw new Error("UNIT confirmation must own a signal");
    view.unmount();
    expect(subscriptions.length).toBeGreaterThan(0);
    for (const unsubscribe of subscriptions) expect(unsubscribe).toHaveBeenCalledOnce();
    expect(signal.aborted).toBe(true);
    await act(async () => { owner.resumeWorkspaceOwner(); });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(["dispatch", "adoption", "open"] as const)(
    "holds a same-token suspension after a returned actual confirmation before %s",
    async (stage) => {
      const captured = owner.workspaceOwnerSession();
      const originalConfirm = owner.awaitWorkspaceOwnerSession;
      const suspendAt = stage === "dispatch" ? 1 : stage === "adoption" ? 2 : 3;
      let confirmations = 0;
      vi.spyOn(owner, "awaitWorkspaceOwnerSession").mockImplementation((session, signal) => {
        const pending = originalConfirm(session, signal);
        confirmations += 1;
        if (confirmations === suspendAt) {
          void pending.then((admitted) => {
            if (admitted) act(() => { owner.suspendWorkspaceOwner(); });
          });
        }
        return pending;
      });
      fetchMock.mockResolvedValueOnce(unitResult());
      const onOpen = vi.fn();
      render(<CorpusSearch onOpen={onOpen} />);
      typeQuery("unit query"); submit();
      if (stage === "open") {
        await screen.findByText(unitTitle);
        fireEvent.click(screen.getByRole("button", { name: /UNIT search result/ }));
      }
      await waitFor(() => expect(owner.workspaceOwnerAdmission().state).toBe("suspended"));
      if (stage === "dispatch") expect(fetchMock).not.toHaveBeenCalled();
      if (stage === "adoption") expect(screen.queryByText(unitTitle)).toBeNull();
      expect(onOpen).not.toHaveBeenCalled();
      act(() => { expect(owner.resumeWorkspaceOwner(captured)).toBe(true); });
      if (stage === "open") await waitFor(() => expect(onOpen).toHaveBeenCalledWith(unitHit.document_id, 4));
      else await screen.findByText(unitTitle);
      expect(fetchMock).toHaveBeenCalledOnce();
      expect(owner.workspaceOwnerSession()).toBe(captured);
    },
  );

  it.each(["null", "failed"] as const)("refuses dispatch for %s owner admission", (state) => {
    const confirmation = vi.spyOn(owner, "awaitWorkspaceOwnerSession");
    if (state === "null") owner.setWorkspaceOwner(null);
    if (state === "failed") {
      const failure = new Error("synthetic admission failure");
      const dispose = observe((snapshot) => { if (snapshot.state === "suspended") throw failure; });
      expect(() => owner.suspendWorkspaceOwner()).toThrow(failure);
      dispose();
    }
    render(<CorpusSearch onOpen={vi.fn()} />);
    typeQuery("unit private query"); submit();
    expect(confirmation).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
