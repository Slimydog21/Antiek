import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import type { NotebookResponse } from "./types";

const { getNotebookMock, appendNotebookBlockMock } = vi.hoisted(() => ({
  getNotebookMock: vi.fn(),
  appendNotebookBlockMock: vi.fn(),
}));

vi.mock("../../lib/api", () => ({
  getNotebook: getNotebookMock,
  appendNotebookBlock: appendNotebookBlockMock,
  deleteNotebookBlock: vi.fn(),
  patchNotebookBlock: vi.fn(),
  reorderNotebookBlocks: vi.fn(),
}));
vi.mock("../../lib/analytics", () => ({ track: vi.fn() }));
vi.mock("../../components/ArtifactExport", () => ({ ArtifactExport: () => null }));
vi.mock("./NotebookCanvas", () => ({
  default: ({ notebook, onAppendBlock }: {
    notebook: NotebookResponse;
    onAppendBlock: (block: { block_type: string; content: unknown }) => Promise<void>;
  }) => (
    <section aria-label="Notebook content">
      <h1>{notebook.title}</h1>
      <button onClick={() => void onAppendBlock({ block_type: "prose", content: { text: "note" } })}>
        Add note
      </button>
    </section>
  ),
}));

import Notebook from "./index";

function notebook(id: string, title = id): NotebookResponse {
  return {
    notebook_id: id, title, investigation_id: null, document_id: null,
    content_class: "user_owned", created_at: "2026-10-06", updated_at: "2026-10-06", blocks: [],
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function mount() {
  render(
    <MemoryRouter initialEntries={["/notebook/A"]}>
      <Link to="/notebook/B">Open B</Link>
      <Link to="/notebook/A">Open A</Link>
      <Routes><Route path="/notebook/:notebookId" element={<Notebook />} /></Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => { vi.resetAllMocks(); });
afterEach(cleanup);

describe("Notebook route continuity (API-boundary unit regressions)", () => {
  it("removes A's editable content while B loads and when B is refused", async () => {
    const b = deferred<NotebookResponse>();
    getNotebookMock.mockResolvedValueOnce(notebook("A")).mockReturnValueOnce(b.promise);
    await act(async () => mount());
    expect(screen.getByText("A")).toBeTruthy();
    await act(async () => fireEvent.click(screen.getByText("Open B")));
    await waitFor(() => expect(getNotebookMock).toHaveBeenCalledWith("B"));
    expect(screen.queryByText("A")).toBeNull();
    expect(screen.queryByText("Add note")).toBeNull();
    await act(async () => b.reject(new Error("B refused: HTTP 403")));
    expect(screen.getByText("B refused: HTTP 403")).toBeTruthy();
    expect(screen.queryByText("Add note")).toBeNull();
    expect(appendNotebookBlockMock).not.toHaveBeenCalled();
  });

  it("keeps B open when an earlier load of A resolves late", async () => {
    const a = deferred<NotebookResponse>();
    getNotebookMock.mockReturnValueOnce(a.promise).mockResolvedValueOnce(notebook("B"));
    await act(async () => mount());
    await waitFor(() => expect(getNotebookMock).toHaveBeenCalledWith("A"));
    await act(async () => fireEvent.click(screen.getByText("Open B")));
    expect(screen.getByText("B")).toBeTruthy();
    await act(async () => a.resolve(notebook("A")));
    expect(screen.getByText("B")).toBeTruthy();
    expect(screen.queryByText("A")).toBeNull();
  });

  it("does not replace B with the result of an edit made in A", async () => {
    const savedA = deferred<NotebookResponse>();
    getNotebookMock.mockResolvedValueOnce(notebook("A")).mockResolvedValueOnce(notebook("B"));
    appendNotebookBlockMock.mockReturnValue(savedA.promise);
    await act(async () => mount());
    expect(screen.getByText("A")).toBeTruthy();
    await act(async () => fireEvent.click(screen.getByText("Add note")));
    await waitFor(() => expect(appendNotebookBlockMock).toHaveBeenCalledWith("A", {
      block_type: "prose", content: { text: "note" },
    }));
    await act(async () => fireEvent.click(screen.getByText("Open B")));
    expect(screen.getByText("B")).toBeTruthy();
    await act(async () => savedA.resolve(notebook("A", "A saved")));
    expect(screen.getByText("B")).toBeTruthy();
    expect(screen.queryByText("A saved")).toBeNull();
  });
  it("keeps a freshly reopened A when its previous edit resolves after A → B → A", async () => {
    const oldSave = deferred<NotebookResponse>();
    getNotebookMock.mockResolvedValueOnce(notebook("A"))
      .mockResolvedValueOnce(notebook("B"))
      .mockResolvedValueOnce(notebook("A", "A fresh"));
    appendNotebookBlockMock.mockReturnValue(oldSave.promise);
    await act(async () => mount());
    expect(screen.getByText("A")).toBeTruthy();
    await act(async () => fireEvent.click(screen.getByText("Add note")));
    await act(async () => fireEvent.click(screen.getByText("Open B")));
    expect(screen.getByText("B")).toBeTruthy();
    await act(async () => fireEvent.click(screen.getByText("Open A")));
    expect(screen.getByText("A fresh")).toBeTruthy();
    await act(async () => oldSave.resolve(notebook("A", "A old save")));
    expect(screen.getByText("A fresh")).toBeTruthy();
    expect(screen.queryByText("A old save")).toBeNull();
  });

});
