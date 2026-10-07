import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { BookDetail, FullTextResponse } from "../../api/books";
import { ApiError } from "../../lib/api";
import { resetReadingStateBus, setReadingStateOwner } from "../../hooks/useReadingState";
import { positionStorageKey } from "./usePosition";

// These synthetic API-boundary fixtures test the real reader and position
// hooks. They are unit evidence, not a successful live catalogue/book read.
const { detail, body, houses } = vi.hoisted(() => ({
  detail: vi.fn<(id: string) => Promise<BookDetail>>(),
  body: vi.fn<(id: string) => Promise<FullTextResponse>>(),
  houses: vi.fn(),
}));
vi.mock("../../api/books", async (original) => ({
  ...await original<typeof import("../../api/books")>(),
  getBook: detail,
  getBookFullText: body,
  listBooks: houses,
}));
import BookReader from "./index";

function book(id: string, count: number): BookDetail {
  return {
    document_id: id, title: `Unit book ${id}`, author: null,
    servability: "public_domain", servable_full_text: true,
    page_count: count, cover_uri: null, ip_holder_id: null,
    taken_down: false, pagination_scheme: "pdf_page",
    provenance: null, license_basis: null, toc: [],
  };
}

function text(id: string, count: number): FullTextResponse {
  return {
    document_id: id, title: `Unit book ${id}`, author: null,
    servability: "public_domain", servable: true,
    full_text: Array.from({ length: count }, (_, i) => `## Page ${i + 1}\n\nUnit ${id} passage ${i + 1}.`).join("\n\n"),
    snippet: null, reason: "servable", tier: null, ad_eligible: false,
    canonical_url: null, license: null,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (cause: unknown) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function tree(id: string) {
  return <MemoryRouter><BookReader documentId={id} /></MemoryRouter>;
}

beforeEach(() => {
  window.sessionStorage.clear();
  setReadingStateOwner("unit-reader");
  resetReadingStateBus();
  detail.mockReset().mockImplementation(async (id) => book(id, id === "short" ? 2 : 8));
  body.mockReset().mockImplementation(async (id) => text(id, id === "short" ? 2 : 8));
  houses.mockReset().mockResolvedValue({ books: [], count: 0 });
  // The real reading-state/anchor/fork transports fail. The owner/book
  // sessionStorage fallback must carry reading without a fabricated row.
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("controlled ancillary outage")));
});

afterEach(() => {
  cleanup();
  resetReadingStateBus();
  setReadingStateOwner(null);
  vi.unstubAllGlobals();
});

describe("operational reading load and return", () => {
  it("renders the loaded body while the optional house catalogue is pending", async () => {
    const pendingHouses = deferred<{ books: []; count: number }>();
    houses.mockReturnValue(pendingHouses.promise);
    render(tree("short"));

    await screen.findByText("Unit short passage 1.");
    expect(screen.queryByText("Opening the book…")).toBeNull();
    await act(async () => pendingHouses.reject(new ApiError("unit unavailable", 503, "")));
    expect(screen.getByText("Unit short passage 1.")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does not clamp the next book's saved page against the previous book while loading", async () => {
    const pendingDetail = deferred<BookDetail>();
    const pendingBody = deferred<FullTextResponse>();
    const savedKey = positionStorageKey("long");
    window.sessionStorage.setItem(savedKey, "6");
    const view = render(tree("short"));
    await screen.findByText("Unit short passage 1.");
    detail.mockReturnValueOnce(pendingDetail.promise);
    body.mockReturnValueOnce(pendingBody.promise);

    view.rerender(tree("long"));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Opening the book"));
    expect(window.sessionStorage.getItem(savedKey)).toBe("6");

    await act(async () => {
      pendingDetail.resolve(book("long", 8));
      pendingBody.resolve(text("long", 8));
    });
    await screen.findByText("Unit long passage 7.");
    expect(window.sessionStorage.getItem(savedKey)).toBe("6");
  });

  it("preserves the next book's saved page when its load is rejected", async () => {
    const savedKey = positionStorageKey("long");
    window.sessionStorage.setItem(savedKey, "6");
    const view = render(tree("short"));
    await screen.findByText("Unit short passage 1.");
    detail.mockRejectedValueOnce(new ApiError("unit signed out", 401, ""));
    body.mockRejectedValueOnce(new ApiError("unit signed out", 401, ""));

    view.rerender(tree("long"));
    await screen.findByRole("alert");
    expect(window.sessionStorage.getItem(savedKey)).toBe("6");
    expect(screen.queryByText("Unit short passage 1.")).toBeNull();
  });

  it("restores the owner/book page after leaving and resetting the in-memory bus during an outage", async () => {
    const savedKey = positionStorageKey("long");
    window.sessionStorage.setItem(savedKey, "6");
    const first = render(tree("long"));
    await screen.findByText("Unit long passage 7.");
    first.unmount();
    resetReadingStateBus();

    render(tree("long"));
    await screen.findByText("Unit long passage 7.");
    expect(window.sessionStorage.getItem(savedKey)).toBe("6");
  });
});
