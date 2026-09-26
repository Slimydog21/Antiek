/**
 * FFX SPR-03 (F-07, A-14): /notebook/:id rendered "GET /notebooks/<id> failed:
 * HTTP 404", and the four block actions landed raw strings in the same sink.
 * Every failure must be plain copy; a failed block action must leave the
 * notebook on screen.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// The canvas (TipTap) and export menu are not under test: a stub exposes the
// blocks and one "add" affordance wired to the real onAppendBlock.
vi.mock("./NotebookCanvas", () => ({
  default: (props: {
    notebook: { blocks: { block_id: string }[] };
    onAppendBlock: (req: { block_type: string; content: unknown }) => Promise<void>;
  }) => (
    <div>
      <ul>
        {props.notebook.blocks.map((b) => (
          <li key={b.block_id}>{b.block_id}</li>
        ))}
      </ul>
      <button type="button" onClick={() => void props.onAppendBlock({ block_type: "prose", content: { text: "hi" } })}>
        stub add block
      </button>
    </div>
  ),
}));
vi.mock("../../components/ArtifactExport", () => ({ ArtifactExport: () => null }));
vi.mock("../../lib/analytics", () => ({ track: vi.fn() }));

import Notebook from "./index";

const NOTEBOOK = {
  notebook_id: "nb-1",
  title: "My notebook",
  investigation_id: null,
  document_id: null,
  content_class: "user_owned",
  created_at: "2026-09-27",
  updated_at: "2026-09-27",
  blocks: [
    { block_id: "blk-a", block_index: 0, block_type: "prose", ref_id: null, content_json: {}, created_at: "" },
    { block_id: "blk-b", block_index: 1, block_type: "prose", ref_id: null, content_json: {}, created_at: "" },
  ],
};

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function expectHonest(text: string) {
  expect(text).not.toMatch(/\b[45]\d\d\b/);
  expect(text).not.toMatch(/\/[a-z-]+/);
  expect(text).not.toContain("Failed to fetch");
  expect(text).not.toContain("HTTP");
}

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
const fail = (status: number) => new Response(JSON.stringify({ detail: "x" }), { status });

function renderAt(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/notebook/${id}`]}>
      <Routes>
        <Route path="/notebook/:notebookId" element={<Notebook />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Notebook — honest failure", () => {
  it("a 503 on load shows plain copy and Try again reloads the notebook", async () => {
    fetchMock.mockResolvedValueOnce(fail(503)).mockResolvedValueOnce(ok(NOTEBOOK));
    renderAt("nb-1");
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expect(alert.textContent).toContain("Couldn't open this notebook.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("blk-a")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(String(fetchMock.mock.calls[1][0])).toBe(String(fetchMock.mock.calls[0][0]));
  });

  it("a network TypeError on load never shows 'Failed to fetch'", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    renderAt("nb-1");
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
  });

  it("a 404 for a nonexistent id shows no path, no status, and no Try again", async () => {
    fetchMock.mockResolvedValue(fail(404));
    renderAt("does-not-exist");
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("a failed block add keeps the notebook on screen and shows the failure inline", async () => {
    fetchMock
      .mockResolvedValueOnce(ok(NOTEBOOK))
      .mockResolvedValueOnce(fail(503))
      .mockResolvedValueOnce(ok({ ...NOTEBOOK, blocks: [...NOTEBOOK.blocks, { ...NOTEBOOK.blocks[0], block_id: "blk-c", block_index: 2 }] }));
    renderAt("nb-1");
    await screen.findByText("blk-a");
    await userEvent.click(screen.getByRole("button", { name: "stub add block" }));
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expect(alert.textContent).toContain("Couldn't add the block.");
    // The notebook is still there: no whole-page replacement.
    expect(screen.getByText("blk-a")).toBeTruthy();
    expect(screen.getByText("blk-b")).toBeTruthy();
    // Try again re-sends the same append.
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("blk-c")).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(fetchMock.mock.calls[2][1]?.body).toBe(fetchMock.mock.calls[1][1]?.body);
  });
});
