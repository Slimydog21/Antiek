import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";

import type { NotebookResponse } from "./types";

const api = vi.hoisted(() => ({
  getNotebook: vi.fn(),
  appendNotebookBlock: vi.fn(),
  deleteNotebookBlock: vi.fn(),
  patchNotebookBlock: vi.fn(),
  reorderNotebookBlocks: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  getNotebook: api.getNotebook,
  appendNotebookBlock: api.appendNotebookBlock,
  deleteNotebookBlock: api.deleteNotebookBlock,
  patchNotebookBlock: api.patchNotebookBlock,
  reorderNotebookBlocks: api.reorderNotebookBlocks,
}));

vi.mock("./NotebookCanvas", () => ({
  default: ({ notebook }: { notebook: NotebookResponse }) => (
    <section>
      <h1>{notebook.title}</h1>
      <p>{notebook.notebook_id}</p>
    </section>
  ),
}));

import Notebook from "./index";

function notebook(notebookId: string, title: string): NotebookResponse {
  return {
    notebook_id: notebookId,
    title,
    investigation_id: null,
    document_id: null,
    content_class: "user_owned",
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-01T00:00:00Z",
    blocks: [],
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function RouteSwitchProbe() {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate("/notebook/nb-fresh")}>
      open fresh notebook
    </button>
  );
}

beforeEach(() => {
  api.getNotebook.mockReset();
  api.appendNotebookBlock.mockReset();
  api.deleteNotebookBlock.mockReset();
  api.patchNotebookBlock.mockReset();
  api.reorderNotebookBlocks.mockReset();
});

afterEach(cleanup);

describe("Notebook routed container", () => {
  it("keeps stale notebook loads from overwriting the active routed notebook", async () => {
    const stale = deferred<NotebookResponse>();
    const fresh = deferred<NotebookResponse>();
    api.getNotebook.mockReturnValueOnce(stale.promise).mockReturnValueOnce(fresh.promise);

    render(
      <MemoryRouter initialEntries={["/notebook/nb-stale"]}>
        <RouteSwitchProbe />
        <Routes>
          <Route path="/notebook/:notebookId" element={<Notebook />} />
        </Routes>
      </MemoryRouter>,
    );

    await userEvent.click(screen.getByRole("button", { name: /open fresh notebook/i }));
    await act(async () => {
      fresh.resolve(notebook("nb-fresh", "Fresh notebook"));
    });

    expect(await screen.findByText("Fresh notebook")).toBeTruthy();

    await act(async () => {
      stale.resolve(notebook("nb-stale", "Stale notebook"));
    });

    expect(screen.getByText("Fresh notebook")).toBeTruthy();
    expect(screen.queryByText("Stale notebook")).toBeNull();
  });
});
