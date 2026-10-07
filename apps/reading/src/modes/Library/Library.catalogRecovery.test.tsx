import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { LibraryCatalogHttpError, type LibraryPage, type fetchLibraryCatalog } from "../../api/libraryCatalog";
import type { listInvestigations } from "../../lib/api";
import type { curateBooks } from "../../api/books";
import Library from "./index";

const { catalog, investigations, curate } = vi.hoisted(() => ({
  catalog: vi.fn<typeof fetchLibraryCatalog>(),
  investigations: vi.fn<typeof listInvestigations>(),
  curate: vi.fn<typeof curateBooks>(),
}));

vi.mock("../../api/libraryCatalog", async (original) => ({
  ...await original<typeof import("../../api/libraryCatalog")>(),
  fetchLibraryCatalog: catalog,
}));
vi.mock("../../lib/api", async (original) => ({
  ...await original<typeof import("../../lib/api")>(),
  listInvestigations: investigations,
}));
vi.mock("../../api/books", async (original) => ({
  ...await original<typeof import("../../api/books")>(),
  curateBooks: curate,
}));

function mount() {
  return render(<MemoryRouter><Library /></MemoryRouter>);
}

function pendingFailure() {
  const slot: { reject?: (error: Error) => void } = {};
  const promise = new Promise<LibraryPage>((_, reject) => { slot.reject = reject; });
  return {
    promise,
    reject(error: Error) {
      if (!slot.reject) throw new Error("Missing deferred rejection callback");
      slot.reject(error);
    },
  };
}

async function failedShelf() {
  await waitFor(() => {
    expect(screen.getByRole("alert").textContent).toContain("catalog is unavailable");
    expect(screen.queryByRole("status")).toBeNull();
  });
}

beforeEach(() => {
  catalog.mockReset().mockRejectedValue(new LibraryCatalogHttpError(500));
  investigations.mockReset();
  curate.mockReset();
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// Failure-only UNIT controls: no successful catalogue, book, account or provider fixture.
describe("Primary Library catalog read recovery", () => {
  it("offers an explicit Retry after a failed catalogue read", async () => {
    mount();
    await failedShelf();
    expect(screen.getByRole("button", { name: "Retry catalog" })).toBeTruthy();
    expect(screen.queryByText(/0 books readable in full/)).toBeNull();
    expect(screen.queryByText(/Nothing is readable in full/)).toBeNull();
  });

  it("reissues only the same catalogue GET and keeps a second failure honest", async () => {
    mount();
    await failedShelf();
    const original = catalog.mock.calls[0][0];
    expect(original).toEqual({ filter: "servable", search: "", page: 1, page_size: 20 });
    fireEvent.click(screen.getByRole("button", { name: "Retry catalog" }));
    await waitFor(() => expect(catalog).toHaveBeenCalledTimes(2));
    await failedShelf();
    expect(catalog.mock.calls[1][0]).toEqual(original);
    expect(investigations).not.toHaveBeenCalled();
    expect(curate).not.toHaveBeenCalled();
  });

  it("retries the currently selected Preview filter", async () => {
    mount();
    await failedShelf();
    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));
    await waitFor(() => expect(catalog).toHaveBeenCalledTimes(2));
    await failedShelf();
    fireEvent.click(screen.getByRole("button", { name: "Retry catalog" }));
    await waitFor(() => expect(catalog).toHaveBeenCalledTimes(3));
    expect(catalog.mock.calls[2][0]).toEqual({ filter: "gated", search: "", page: 1, page_size: 20 });
  });

  it("retries the submitted search without changing its query", async () => {
    mount();
    await failedShelf();
    fireEvent.change(screen.getByRole("searchbox", { name: "Search catalog by title or author" }), { target: { value: "  epistemology  " } });
    fireEvent.click(screen.getByRole("button", { name: "Search catalog" }));
    await waitFor(() => expect(catalog).toHaveBeenCalledTimes(2));
    await failedShelf();
    fireEvent.click(screen.getByRole("button", { name: "Retry catalog" }));
    await waitFor(() => expect(catalog).toHaveBeenCalledTimes(3));
    expect(catalog.mock.calls[2][0]).toEqual({ filter: "servable", search: "epistemology", page: 1, page_size: 20 });
  });

  it("retains focus in the same panel while Retry is replaced by loading", async () => {
    const pending = pendingFailure();
    catalog.mockRejectedValueOnce(new LibraryCatalogHttpError(500)).mockReturnValueOnce(pending.promise);
    mount();
    await failedShelf();
    const panel = screen.getByRole("tabpanel");
    const retry = screen.getByRole("button", { name: "Retry catalog" });
    retry.focus();
    fireEvent.click(retry);
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Opening the library"));
    expect(screen.queryByRole("button", { name: "Retry catalog" })).toBeNull();
    expect(document.activeElement).toBe(panel);
    pending.reject(new LibraryCatalogHttpError(403));
    await failedShelf();
    expect(document.activeElement).toBe(panel);
  });

  it("keeps an unsubmitted curation draft and never invokes curation on Retry", async () => {
    mount();
    await failedShelf();
    const prompt = screen.getByRole("textbox", { name: "Curate the library by prompt" });
    fireEvent.change(prompt, { target: { value: "my reading question" } });
    fireEvent.click(screen.getByRole("button", { name: "Retry catalog" }));
    await waitFor(() => expect(catalog).toHaveBeenCalledTimes(2));
    await failedShelf();
    expect(screen.getByDisplayValue("my reading question")).toBe(prompt);
    expect(curate).not.toHaveBeenCalled();
  });

  it("retires the retry request when the mounted Library leaves", async () => {
    const pending = pendingFailure();
    catalog.mockRejectedValueOnce(new LibraryCatalogHttpError(500)).mockReturnValueOnce(pending.promise);
    const view = mount();
    await failedShelf();
    fireEvent.click(screen.getByRole("button", { name: "Retry catalog" }));
    await waitFor(() => expect(catalog).toHaveBeenCalledTimes(2));
    const signal = catalog.mock.calls[1][1];
    if (!signal) throw new Error("Retry GET did not receive its lifetime signal");
    expect(signal.aborted).toBe(false);
    view.unmount();
    expect(signal.aborted).toBe(true);
    pending.reject(new LibraryCatalogHttpError(500));
  });

  it("refuses an old retry completion after the filter changes", async () => {
    const old = pendingFailure();
    const current = pendingFailure();
    catalog.mockRejectedValueOnce(new LibraryCatalogHttpError(500)).mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    mount();
    await failedShelf();
    fireEvent.click(screen.getByRole("button", { name: "Retry catalog" }));
    await waitFor(() => expect(catalog).toHaveBeenCalledTimes(2));
    const oldSignal = catalog.mock.calls[1][1];
    if (!oldSignal) throw new Error("Retry GET did not receive its lifetime signal");
    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));
    await waitFor(() => expect(catalog).toHaveBeenCalledTimes(3));
    expect(oldSignal.aborted).toBe(true);
    await act(async () => {
      old.reject(new LibraryCatalogHttpError(500));
      await old.promise.catch(() => undefined);
    });
    expect(screen.getByRole("status").textContent).toContain("Opening the library");
    expect(screen.queryByRole("alert")).toBeNull();
    current.reject(new LibraryCatalogHttpError(403));
    await failedShelf();
    expect(catalog.mock.calls[2][0]?.filter).toBe("gated");
  });

  it("offers manual recovery after the bounded busy retries are exhausted", async () => {
    catalog.mockRejectedValue(new LibraryCatalogHttpError(503));
    mount();
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain("library is busy");
      expect(screen.queryByRole("status")).toBeNull();
    });
    expect(catalog).toHaveBeenCalledTimes(3);
    const next = pendingFailure();
    catalog.mockReturnValueOnce(next.promise);
    fireEvent.click(screen.getByRole("button", { name: "Retry catalog" }));
    await waitFor(() => expect(catalog).toHaveBeenCalledTimes(4));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("Opening the library");
    next.reject(new LibraryCatalogHttpError(403));
    await failedShelf();
    expect(catalog).toHaveBeenCalledTimes(4);
  });
});
