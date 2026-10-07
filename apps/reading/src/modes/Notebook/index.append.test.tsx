import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { NotebookResponse } from "./types";

const { getNotebookMock, appendNotebookBlockMock, trackMock } = vi.hoisted(() => ({
  getNotebookMock: vi.fn(),
  appendNotebookBlockMock: vi.fn(),
  trackMock: vi.fn(),
}));

vi.mock("../../lib/api", () => ({
  getNotebook: getNotebookMock,
  appendNotebookBlock: appendNotebookBlockMock,
  patchNotebookBlock: vi.fn(),
  deleteNotebookBlock: vi.fn(),
  reorderNotebookBlocks: vi.fn(),
}));
vi.mock("../../lib/analytics", () => ({ track: trackMock }));
vi.mock("../../components/ArtifactExport", () => ({ ArtifactExport: () => null }));

// The route, canvas and modal (including its Escape handler) are real.
import Notebook from "./index";

function notebook(text?: string): NotebookResponse {
  return {
    notebook_id: "notebook-append", title: "Append controls", investigation_id: null,
    document_id: null, content_class: "user_owned", created_at: "2026-10-06",
    updated_at: "2026-10-06", blocks: text ? [{
      block_id: "prose-one", block_index: 0, block_type: "prose", ref_id: null,
      content_json: { text }, created_at: "2026-10-06",
    }] : [],
  };
}

beforeEach(async () => {
  vi.resetAllMocks();
  getNotebookMock.mockResolvedValue(notebook());
  await act(async () => {
    render(
      <MemoryRouter initialEntries={["/notebook/notebook-append"]}>
        <Routes><Route path="/notebook/:notebookId" element={<Notebook />} /></Routes>
      </MemoryRouter>,
    );
  });
  await screen.findByText("+ add block");
});

function openAppend(kind: string) {
  fireEvent.click(screen.getByText("+ add block"));
  fireEvent.click(screen.getByText(kind));
}

function submitButton() {
  const button = document.querySelector("[role=dialog] footer button:last-child");
  if (!button) throw new Error("Append submit button is absent");
  return button;
}

afterEach(cleanup);

describe("Notebook append outcomes (API-boundary unit regressions)", () => {
  it("retains refused prose and closes only after a successful manual retry", async () => {
    appendNotebookBlockMock.mockRejectedValueOnce(new Error("POST refused: HTTP 403"))
      .mockResolvedValueOnce(notebook("Draft prose"));
    openAppend("Prose");
    fireEvent.change(screen.getByLabelText("Prose text"), { target: { value: "Draft prose" } });
    await act(async () => fireEvent.click(submitButton()));
    expect(screen.getByDisplayValue("Draft prose")).toHaveProperty("disabled", false);
    expect(screen.getByText("POST refused: HTTP 403")).toBeTruthy();
    expect(trackMock).not.toHaveBeenCalled();
    expect(appendNotebookBlockMock).toHaveBeenNthCalledWith(1,
      "notebook-append", { block_type: "prose", content: { text: "Draft prose" } });
    await act(async () => fireEvent.click(submitButton()));
    expect(appendNotebookBlockMock).toHaveBeenNthCalledWith(2,
      "notebook-append", { block_type: "prose", content: { text: "Draft prose" } });
    expect(document.querySelector("[role=dialog]")).toBeNull();
    expect(screen.getByText("Draft prose")).toBeTruthy();
    expect(screen.queryByText("POST refused: HTTP 403")).toBeNull();
    expect(trackMock).toHaveBeenCalledExactlyOnceWith("notebook_block_appended", { block_type: "prose" });
  });

  it("keeps a pending draft, consumes Escape, and refuses duplicate submit or dismissal", async () => {
    let finish: (value: NotebookResponse) => void = () => { throw new Error("Request not started"); };
    appendNotebookBlockMock.mockReturnValue(new Promise<NotebookResponse>((resolve) => { finish = resolve; }));
    openAppend("Prose");
    fireEvent.change(screen.getByLabelText("Prose text"), { target: { value: "Pending prose" } });
    await act(async () => fireEvent.click(submitButton()));
    expect(screen.getByDisplayValue("Pending prose")).toHaveProperty("disabled", true);
    expect(submitButton()).toHaveProperty("disabled", true);
    expect(screen.getByText("Cancel")).toHaveProperty("disabled", true);
    const form = document.querySelector("[role=dialog] form");
    if (!form) throw new Error("Pending append form is absent");
    fireEvent.submit(form);
    fireEvent.click(submitButton());
    fireEvent.click(screen.getByLabelText("Close"));
    const dialog = document.querySelector("[role=dialog]");
    if (!dialog?.parentElement) throw new Error("Pending modal is absent");
    fireEvent.mouseDown(dialog.parentElement);
    const escape = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    fireEvent(window, escape);
    expect(escape.defaultPrevented).toBe(true);
    expect(document.querySelector("[role=dialog]")).toBe(dialog);
    expect(appendNotebookBlockMock).toHaveBeenCalledTimes(1);
    expect(trackMock).not.toHaveBeenCalled();
    await act(async () => finish(notebook("Pending prose")));
    expect(document.querySelector("[role=dialog]")).toBeNull();
    expect(screen.getByText("Pending prose")).toBeTruthy();
  });

  it.each([
    { picker: "Claim reference", primary: "Claim ID to embed", secondary: "Display text for the claim (optional)", block_type: "claim_card", content: { text: "Source text" } },
    { picker: "Region embed", primary: "Region ID to embed", secondary: "Cached excerpt text (optional)", block_type: "region_embed", content: { excerpt: "Source text" } },
  ])("preserves both $block_type fields and their payload mapping after refusal", async (kind) => {
    appendNotebookBlockMock.mockRejectedValue(new Error("Append request failed"));
    openAppend(kind.picker);
    fireEvent.change(screen.getByLabelText(kind.primary), { target: { value: " reference-id " } });
    fireEvent.change(screen.getByLabelText(kind.secondary), { target: { value: " Source text " } });
    await act(async () => fireEvent.click(submitButton()));
    expect(screen.getByLabelText(kind.primary)).toHaveProperty("value", " reference-id ");
    expect(screen.getByLabelText(kind.secondary)).toHaveProperty("value", " Source text ");
    expect(screen.getByLabelText(kind.primary)).toHaveProperty("disabled", false);
    expect(screen.getByLabelText(kind.secondary)).toHaveProperty("disabled", false);
    expect(screen.getByText("Append request failed")).toBeTruthy();
    expect(appendNotebookBlockMock).toHaveBeenCalledExactlyOnceWith("notebook-append", {
      block_type: kind.block_type, ref_id: "reference-id", content: kind.content,
    });
    const escape = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    fireEvent(window, escape);
    expect(escape.defaultPrevented).toBe(true);
    expect(document.querySelector("[role=dialog]")).toBeNull();
    fireEvent.click(screen.getByText("+ add block"));
    fireEvent.click(screen.getByText(kind.picker));
    expect(screen.getByLabelText(kind.primary)).toHaveProperty("value", "");
    expect(screen.getByLabelText(kind.secondary)).toHaveProperty("value", "");
    expect(screen.queryByText("Append request failed")).toBeNull();
  });

  it("allows cancelling an idle draft without making a request", async () => {
    openAppend("Prose");
    fireEvent.change(screen.getByLabelText("Prose text"), { target: { value: "Local draft" } });
    fireEvent.click(screen.getByText("Cancel"));
    expect(document.querySelector("[role=dialog]")).toBeNull();
    expect(appendNotebookBlockMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("+ add block"));
    fireEvent.click(screen.getByText("Prose"));
    expect(screen.getByLabelText("Prose text")).toHaveProperty("value", "");
  });
});
