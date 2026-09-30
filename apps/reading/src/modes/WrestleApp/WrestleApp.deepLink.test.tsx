import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

/**
 * /wrestle/:documentId is linked from Documents, the command palette, the
 * citation modal and the project tree. Before this fix every one of those
 * links landed on the generic "Load a PDF to wrestle." page, because Wrestle
 * only opens bytes chosen from the reader's computer. The deep link must now
 * say what the id is and where it can be read.
 */

const { getBookMock } = vi.hoisted(() => ({ getBookMock: vi.fn() }));

vi.mock("../../api/books", async (orig) => ({
  ...(await orig<typeof import("../../api/books")>()),
  getBook: getBookMock,
}));
vi.mock("../../hooks/useEventStream", () => ({
  useEventStream: () => ({ events: [], status: "open", reconnects: 0 }),
}));
vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock("../../components/PdfViewer", () => ({ default: () => <div>PDF</div> }));

import WrestleApp from "./index";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/wrestle" element={<WrestleApp />} />
        <Route path="/wrestle/:documentId" element={<WrestleApp />} />
        <Route path="/read/:documentId" element={<div>Reader page</div>} />
        <Route path="/documents" element={<div>Documents page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("WrestleApp deep link", () => {
  beforeEach(() => {
    getBookMock.mockReset();
    window.sessionStorage.clear();
  });
  afterEach(cleanup);

  it("names a stored book and opens it in the Reader", async () => {
    getBookMock.mockResolvedValue({ title: "The Origin of Species" });
    renderAt("/wrestle/doc-1");
    expect(screen.getByRole("status").textContent).toContain("Looking up this document…");
    expect(
      await screen.findByRole("heading", { name: "The Origin of Species" }),
    ).toBeTruthy();
    expect(getBookMock).toHaveBeenCalledWith("doc-1");
    expect(screen.queryByText("Load a PDF to wrestle.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open in the Reader" }));
    expect(await screen.findByText("Reader page")).toBeTruthy();
  });

  it("says plainly when nothing is stored for the id", async () => {
    getBookMock.mockRejectedValue(new Error("book_not_found"));
    renderAt("/wrestle/doc-2");
    expect(
      await screen.findByRole("heading", { name: "There's no PDF stored for this document." }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Choose its PDF…" })).toBeTruthy();
    fireEvent.click(screen.getByRole("link", { name: "Back to documents" }));
    expect(await screen.findByText("Documents page")).toBeTruthy();
  });

  it("separates a failed lookup from a missing document and retries", async () => {
    getBookMock
      .mockRejectedValueOnce(new Error("GET /books/{id}: HTTP 502"))
      .mockResolvedValueOnce({ title: "Walden" });
    renderAt("/wrestle/doc-3");
    expect(
      await screen.findByRole("heading", { name: "Couldn't look up this document." }),
    ).toBeTruthy();
    expect(screen.queryByText(/no PDF stored/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Walden" })).toBeTruthy();
    await waitFor(() => expect(getBookMock).toHaveBeenCalledTimes(2));
  });

  it("keeps the plain upload page when no document is linked", () => {
    renderAt("/wrestle");
    expect(screen.getByRole("heading", { name: "Load a PDF to wrestle." })).toBeTruthy();
    expect(getBookMock).not.toHaveBeenCalled();
  });
});
