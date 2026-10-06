import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LibraryView from "./LibraryView";

function pendingResponse() {
  let reject: (error: Error) => void = () => { throw new Error("unassigned request"); };
  const promise = new Promise<Response>((_, fail) => { reject = fail; });
  return { promise, reject };
}

const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal("fetch", fetchMock); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function mount() {
  return render(<MemoryRouter><LibraryView /></MemoryRouter>);
}

describe("Library operational recovery (synthetic failures only)", () => {
  it.each([401, 403, 503])("HTTP %s gives a read-only Retry without an empty/count claim", async (status) => {
    fetchMock.mockResolvedValue(new Response(null, { status }));
    mount();
    await screen.findByRole("alert");
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(screen.queryByText(/0 readable in full/)).toBeNull();
    expect(screen.queryByText(/Nothing is readable/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls.every(([, init]) => init?.method === "GET")).toBe(true);
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      expect.stringContaining("/library?"), expect.stringContaining("/library?"),
    ]);
  });

  it("network failure remains recoverable and does not masquerade as a 404 or empty shelf", async () => {
    fetchMock.mockRejectedValue(new TypeError("Network request failed"));
    mount();
    await screen.findByRole("alert");
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(screen.queryByText(/catalog isn’t available yet/)).toBeNull();
    expect(screen.queryByText(/0 readable/)).toBeNull();
  });

  it("changing filter aborts the old request and refuses its late failure", async () => {
    const old = pendingResponse(); const current = pendingResponse();
    fetchMock.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    mount();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const oldSignal = fetchMock.mock.calls[0][1]?.signal;
    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(oldSignal?.aborted).toBe(true);
    await act(async () => { old.reject(new Error("obsolete request failed")); });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("Opening the library")).toBeTruthy();
    await act(async () => { current.reject(new Error("current request failed")); });
    expect(screen.getByRole("alert").textContent).toContain("current request failed");
  });

  it("unmount aborts the owned catalogue request", async () => {
    const request = pendingResponse(); fetchMock.mockReturnValue(request.promise);
    const view = mount();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const signal = fetchMock.mock.calls[0][1]?.signal;
    view.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => { request.reject(new Error("retired request failed")); });
  });
});
