/**
 * NotebookPage.test — /notebook/:id opens with the shared states.
 *
 * Before: "Loading notebook…" in grey, then the raw error ("Failed to fetch")
 * in red with no way to retry (critique: Notebook/index:136). Design spec §5:
 * loading names what is opening, and an error says what failed and what is
 * safe, with one Try again and the raw message behind Copy error details.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Notebook from "./index";

const { getNotebookMock } = vi.hoisted(() => ({ getNotebookMock: vi.fn() }));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  getNotebook: getNotebookMock,
}));

afterEach(() => {
  cleanup();
  getNotebookMock.mockReset();
});

function renderAt(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/notebook/${id}`]}>
      <Routes>
        <Route path="/notebook/:notebookId" element={<Notebook />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Notebook page states", () => {
  it("names what is opening while the notebook loads", async () => {
    getNotebookMock.mockReturnValue(new Promise(() => {}));
    renderAt("nb-1");
    const status = await screen.findByRole("status");
    expect(status.textContent).toContain("Opening this notebook");
  });

  it("names a failed load, hides the raw message, and retries", async () => {
    getNotebookMock
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce({
        notebook_id: "nb-1",
        title: "Field notes",
        investigation_id: null,
        document_id: null,
        content_class: "user_owned",
        created_at: "2026-09-24T00:00:00Z",
        updated_at: "2026-09-24T00:00:00Z",
        blocks: [],
      });
    renderAt("nb-1");

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Couldn’t open this notebook");
    expect(document.body.textContent).not.toContain("Failed to fetch");

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(getNotebookMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });
});
