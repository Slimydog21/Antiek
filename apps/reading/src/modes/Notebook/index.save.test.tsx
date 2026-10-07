import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { NotebookResponse } from "./types";

const { getNotebookMock, patchNotebookBlockMock } = vi.hoisted(() => ({
  getNotebookMock: vi.fn(),
  patchNotebookBlockMock: vi.fn(),
}));

vi.mock("../../lib/api", () => ({
  getNotebook: getNotebookMock,
  patchNotebookBlock: patchNotebookBlockMock,
  appendNotebookBlock: vi.fn(),
  deleteNotebookBlock: vi.fn(),
  reorderNotebookBlocks: vi.fn(),
}));
vi.mock("../../lib/analytics", () => ({ track: vi.fn() }));
vi.mock("../../components/ArtifactExport", () => ({ ArtifactExport: () => null }));
// This suite exercises the real route and canvas. Modal ownership is separate.
vi.mock("../../components/lemon/LemonModal", () => ({ LemonModal: () => null }));

import Notebook from "./index";

function notebook(text: string): NotebookResponse {
  return {
    notebook_id: "notebook-save", title: "Save controls", investigation_id: null,
    document_id: null, content_class: "user_owned", created_at: "2026-10-06",
    updated_at: "2026-10-06", blocks: [{
      block_id: "prose-one", block_index: 0, block_type: "prose", ref_id: null,
      content_json: { text }, created_at: "2026-10-06",
    }],
  };
}

async function editDraft() {
  getNotebookMock.mockResolvedValue(notebook("Stored prose"));
  await act(async () => {
    render(
      <MemoryRouter initialEntries={["/notebook/notebook-save"]}>
        <Routes><Route path="/notebook/:notebookId" element={<Notebook />} /></Routes>
      </MemoryRouter>,
    );
  });
  fireEvent.doubleClick(await screen.findByText("Stored prose"));
  fireEvent.change(screen.getByDisplayValue("Stored prose"), { target: { value: "Unsaved draft" } });
}

beforeEach(() => { vi.resetAllMocks(); });
afterEach(cleanup);

describe("Notebook save outcomes (API-boundary unit regressions)", () => {
  it("keeps a refused edit visible and retries the same draft before closing", async () => {
    patchNotebookBlockMock.mockRejectedValueOnce(new Error("PATCH refused: HTTP 403"))
      .mockResolvedValueOnce(notebook("Unsaved draft"));
    await editDraft();
    await act(async () => fireEvent.click(screen.getByText("Save")));
    expect(screen.getByDisplayValue("Unsaved draft")).toHaveProperty("value", "Unsaved draft");
    expect(screen.getByText("PATCH refused: HTTP 403").textContent).toContain("PATCH refused: HTTP 403");
    expect(patchNotebookBlockMock).toHaveBeenNthCalledWith(1,
      "notebook-save", "prose-one", { content: { text: "Unsaved draft" } });
    await act(async () => fireEvent.click(screen.getByText("Save")));
    expect(patchNotebookBlockMock).toHaveBeenNthCalledWith(2,
      "notebook-save", "prose-one", { content: { text: "Unsaved draft" } });
    expect(screen.queryByDisplayValue("Unsaved draft")).toBeNull();
    expect(screen.queryByText("PATCH refused: HTTP 403")).toBeNull();
    expect(screen.getByText("Unsaved draft")).toBeTruthy();
  });

  it("holds the submitted draft and prevents another Save until the response", async () => {
    let finish!: (value: NotebookResponse) => void;
    patchNotebookBlockMock.mockReturnValue(new Promise<NotebookResponse>((resolve) => { finish = resolve; }));
    await editDraft();
    await act(async () => fireEvent.click(screen.getByText("Save")));
    expect(screen.getByDisplayValue("Unsaved draft")).toHaveProperty("value", "Unsaved draft");
    expect(screen.getByDisplayValue("Unsaved draft")).toHaveProperty("disabled", true);
    expect(screen.getByText("Cancel")).toHaveProperty("disabled", true);
    expect(screen.getByText("Saving…")).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByText("Saving…"));
    expect(patchNotebookBlockMock).toHaveBeenCalledTimes(1);
    await act(async () => finish(notebook("Unsaved draft")));
    expect(screen.queryByDisplayValue("Unsaved draft")).toBeNull();
    expect(screen.getByText("Unsaved draft")).toBeTruthy();
  });

  it("cancels a local draft without writing and reopens the stored content", async () => {
    await editDraft();
    fireEvent.click(screen.getByText("Cancel"));
    expect(patchNotebookBlockMock).not.toHaveBeenCalled();
    expect(screen.queryByDisplayValue("Unsaved draft")).toBeNull();
    fireEvent.doubleClick(await screen.findByText("Stored prose"));
    expect(screen.getByDisplayValue("Stored prose")).toHaveProperty("value", "Stored prose");
  });
});
