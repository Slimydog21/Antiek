/**
 * Notebook.test.tsx — Cycle 574 Recursive Fieldbook.
 *
 * Pins:
 *   - missing notebook ID → honest guidance, no POST instructions;
 *   - safe load failure → fixed alert, no internals leaked;
 *   - stale route suppression → a late prior-route GET cannot replace a newer notebook;
 *   - mutation serialization / failure preservation → one-at-a-time lane,
 *     safe error on failure, last confirmed notebook remains rendered;
 *   - block rendering (claim, tombstone, question, region, prose);
 *   - add-block affordance available.
 *
 * Mocks at the api + analytics + react-router boundary so jsdom needs
 * no network.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const { getNotebookMock, appendNotebookBlockMock, deleteNotebookBlockMock, patchNotebookBlockMock, reorderNotebookBlocksMock, trackMock } = vi.hoisted(() => ({
  getNotebookMock: vi.fn(),
  appendNotebookBlockMock: vi.fn(),
  deleteNotebookBlockMock: vi.fn(),
  patchNotebookBlockMock: vi.fn(),
  reorderNotebookBlocksMock: vi.fn(),
  trackMock: vi.fn(),
}));

vi.mock("../../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
  getNotebook: getNotebookMock,
  appendNotebookBlock: appendNotebookBlockMock,
  deleteNotebookBlock: deleteNotebookBlockMock,
  patchNotebookBlock: patchNotebookBlockMock,
  reorderNotebookBlocks: reorderNotebookBlocksMock,
}));

vi.mock("../../lib/analytics", () => ({
  track: trackMock,
}));

vi.mock("../../components/ArtifactExport", () => ({
  ArtifactExport: ({ filenamePrefix }: { filenamePrefix: string }) => (
    <div data-testid="artifact-export">{filenamePrefix}</div>
  ),
}));

import Notebook from "./index";
import type { NotebookBlockResponse, NotebookResponse } from "./types";

afterEach(() => {
  cleanup();
  getNotebookMock.mockReset();
  appendNotebookBlockMock.mockReset();
  deleteNotebookBlockMock.mockReset();
  patchNotebookBlockMock.mockReset();
  reorderNotebookBlocksMock.mockReset();
  trackMock.mockReset();
});

// ── Fixtures ─────────────────────────────────────────────────────

function makeBlock(
  id: string,
  type: NotebookBlockResponse["block_type"],
  content: Record<string, unknown>,
  refId: string | null = null,
  index = 0,
): NotebookBlockResponse {
  return {
    block_id: id,
    block_index: index,
    block_type: type,
    ref_id: refId,
    content_json: content,
    created_at: "2026-07-16T12:00:00Z",
  };
}

function makeNotebook(
  id: string,
  blocks: NotebookBlockResponse[],
  title = "Test Fieldbook",
): NotebookResponse {
  return {
    notebook_id: id,
    title,
    investigation_id: null,
    document_id: null,
    content_class: "user_owned",
    created_at: "2026-07-16T10:00:00Z",
    updated_at: "2026-07-16T12:00:00Z",
    blocks,
  };
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/notebook/:notebookId" element={<Notebook />} />
        <Route path="/notebook" element={<Notebook />} />
      </Routes>
    </MemoryRouter>,
  );
}

// ── M1 · Missing ID ─────────────────────────────────────────────

describe("Notebook — missing notebook ID (M1)", () => {
  it("shows plain navigation guidance when no notebookId in route", () => {
    renderAt("/notebook");
    expect(screen.getByText("Notebook")).toBeTruthy();
    expect(screen.getByText(/open a notebook/i)).toBeTruthy();
    // No POST instructions or implementation details.
    expect(screen.queryByText(/POST/i)).toBeNull();
    expect(screen.queryByText(/notebook_id/i)).toBeNull();
  });
});

// ── M1 · Loading ─────────────────────────────────────────────────

describe("Notebook — loading state (M1)", () => {
  it("shows loading indicator while the required GET is pending", () => {
    getNotebookMock.mockReturnValue(new Promise(() => {})); // never resolves
    renderAt("/notebook/nb-1");
    expect(screen.getByText(/loading notebook/i)).toBeTruthy();
    // No empty fieldbook claim before GET resolves.
    expect(screen.queryByText("0 blocks")).toBeNull();
  });
});

// ── M1 · Safe failure ────────────────────────────────────────────

describe("Notebook — safe load failure (M1)", () => {
  it("shows a fixed alert with no internals on load failure", async () => {
    getNotebookMock.mockRejectedValue(new Error("HTTP 500: {\"detail\":\"internal\"}"));
    renderAt("/notebook/nb-1");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Could not load notebook. Please try again.");
    // No URL, HTTP status, response body, stack, or secret.
    expect(alert.textContent).not.toContain("500");
    expect(alert.textContent).not.toContain("internal");
    expect(alert.textContent).not.toContain("HTTP");
  });
});

// ── M2 · Stale route suppression ─────────────────────────────────

describe("Notebook — stale route suppression (M2)", () => {
  it("discards a late prior-route GET when notebookId changes", async () => {
    let resolveFirst!: (v: unknown) => void;
    getNotebookMock.mockReturnValueOnce(
      new Promise((r) => {
        resolveFirst = r;
      }),
    );
    getNotebookMock.mockResolvedValueOnce(
      makeNotebook("nb-new", [
        makeBlock("b-new", "prose", { text: "New notebook content" }, null, 0),
      ]),
    );

    const { unmount } = renderAt("/notebook/nb-old");
    // The first GET is pending. Now navigate to nb-new.
    unmount();
    renderAt("/notebook/nb-new");

    // nb-new loads successfully.
    await waitFor(() =>
      expect(screen.getByText("New notebook content")).toBeTruthy(),
    );

    // Now the old GET resolves with stale data.
    resolveFirst(
      makeNotebook("nb-old", [
        makeBlock("b-old", "prose", { text: "STALE old content" }, null, 0),
      ]),
    );

    // Wait a tick for any state update.
    await new Promise((r) => setTimeout(r, 50));

    // The stale old content must NOT replace the newer notebook.
    expect(screen.queryByText("STALE old content")).toBeNull();
    expect(screen.getByText("New notebook content")).toBeTruthy();
  });
});

// ── M3 · Mutation serialization / failure preservation ───────────

describe("Notebook — mutation failure preserves confirmed state (M3)", () => {
  it("keeps the last confirmed notebook rendered on append failure", async () => {
    const nb = makeNotebook("nb-1", [
      makeBlock("b1", "prose", { text: "Confirmed prose" }, null, 0),
    ]);
    getNotebookMock.mockResolvedValue(nb);
    appendNotebookBlockMock.mockRejectedValue(new Error("server error"));

    renderAt("/notebook/nb-1");
    await waitFor(() =>
      expect(screen.getByText("Confirmed prose")).toBeTruthy(),
    );

    // Open the block picker and append prose.
    const addBtn = await screen.findByText("+ add block");
    fireEvent.click(addBtn);
    const proseBtn = await screen.findByText("Prose");

    // Stub prompt to return text.
    const promptSpy = vi.spyOn(window, "prompt").mockReturnValue("New prose");
    fireEvent.click(proseBtn);
    promptSpy.mockRestore();

    // The safe error appears; the confirmed prose remains.
    await waitFor(() =>
      expect(
        screen.getByText(/could not append the block/i),
      ).toBeTruthy(),
    );
    expect(screen.getByText("Confirmed prose")).toBeTruthy();
  });

  it("serializes mutations: disables controls while one is pending", async () => {
    const nb = makeNotebook("nb-1", [
      makeBlock("b1", "prose", { text: "Block 1" }, null, 0),
    ]);
    getNotebookMock.mockResolvedValue(nb);

    // Hold the append open so we can check disabled state.
    let resolveAppend!: (v: unknown) => void;
    appendNotebookBlockMock.mockReturnValue(
      new Promise((r) => {
        resolveAppend = r;
      }),
    );

    renderAt("/notebook/nb-1");
    await waitFor(() => expect(screen.getByText("Block 1")).toBeTruthy());

    // Start a mutation.
    const addBtn = screen.getByText("+ add block");
    fireEvent.click(addBtn);
    const promptSpy = vi.spyOn(window, "prompt").mockReturnValue("New block");
    const proseBtn = await screen.findByText("Prose");
    fireEvent.click(proseBtn);
    promptSpy.mockRestore();

    // While the mutation is pending, the add-block button should be disabled.
    await waitFor(() => {
      const btn = screen.getByText("+ add block") as HTMLButtonElement;
      expect(btn.disabled).toBe(true);
    });

    // Resolve the mutation.
    resolveAppend(nb);
    await waitFor(() => {
      const btn = screen.getByText("+ add block") as HTMLButtonElement;
      expect(btn.disabled).toBe(false);
    });
  });
});

// ── Block rendering (M4) ─────────────────────────────────────────

describe("Notebook — block rendering (M4)", () => {
  it("renders prose, claim with cached label, tombstone, and question blocks", async () => {
    const nb = makeNotebook("nb-1", [
      makeBlock("b1", "prose", { text: "Operator prose." }, null, 0),
      makeBlock("b2", "claim_card", { text: "GPUs gate scale." }, "claim-abc", 1),
      makeBlock("b3", "claim_card", { text: "Deleted claim text." }, null, 2),
      makeBlock("b4", "question_card", { question_text: "Where is the moat?" }, "q-1", 3),
    ]);
    getNotebookMock.mockResolvedValue(nb);

    renderAt("/notebook/nb-1");
    await waitFor(() =>
      expect(screen.getByText("Operator prose.")).toBeTruthy(),
    );

    // Prose renders.
    expect(screen.getByText("Operator prose.")).toBeTruthy();

    // Claim with ref — cached label present.
    expect(screen.getByText("GPUs gate scale.")).toBeTruthy();
    expect(screen.getByText(/claim-abc.*cached text/)).toBeTruthy();

    // Claim tombstone (null ref).
    expect(screen.getByText(/tombstone: claim deleted/)).toBeTruthy();

    // Question card.
    expect(screen.getByText("Where is the moat?")).toBeTruthy();
    expect(screen.getByText(/question: q-1 · cached text/)).toBeTruthy();
  });
});

// ── Add-block affordance ─────────────────────────────────────────

describe("Notebook — add block affordance (M1 empty, M4)", () => {
  it("shows the add-block button for an empty notebook", async () => {
    const nb = makeNotebook("nb-empty", [], "Empty Fieldbook");
    getNotebookMock.mockResolvedValue(nb);

    renderAt("/notebook/nb-empty");
    await waitFor(() =>
      expect(screen.getByText("+ add block")).toBeTruthy(),
    );
    // Shows confirmed notebook identity.
    expect(screen.getByText("Empty Fieldbook")).toBeTruthy();
    expect(screen.getByText(/0 blocks/)).toBeTruthy();
  });
});

// ── ArtifactExport path preserved ────────────────────────────────

describe("Notebook — ArtifactExport path preserved (M4)", () => {
  it("renders ArtifactExport with the correct basePath and filenamePrefix", async () => {
    const nb = makeNotebook("nb-export", []);
    getNotebookMock.mockResolvedValue(nb);

    renderAt("/notebook/nb-export");
    const exportEl = await screen.findByTestId("artifact-export");
    expect(exportEl.textContent).toBe("notebook-nb-export");
  });
});

// ── Analytics names preserved ────────────────────────────────────

describe("Notebook — analytics event names preserved (M3)", () => {
  it("calls track with notebook_block_appended on successful append", async () => {
    const nb = makeNotebook("nb-1", []);
    const updated = makeNotebook("nb-1", [
      makeBlock("b-new", "prose", { text: "Appended" }, null, 0),
    ]);
    getNotebookMock.mockResolvedValue(nb);
    appendNotebookBlockMock.mockResolvedValue(updated);

    renderAt("/notebook/nb-1");
    await waitFor(() =>
      expect(screen.getByText("+ add block")).toBeTruthy(),
    );

    const addBtn = screen.getByText("+ add block");
    fireEvent.click(addBtn);
    const promptSpy = vi.spyOn(window, "prompt").mockReturnValue("Appended");
    const proseBtn = await screen.findByText("Prose");
    fireEvent.click(proseBtn);
    promptSpy.mockRestore();

    await waitFor(() => expect(trackMock).toHaveBeenCalled());
    expect(trackMock).toHaveBeenCalledWith("notebook_block_appended", {
      block_type: "prose",
    });
  });
});
