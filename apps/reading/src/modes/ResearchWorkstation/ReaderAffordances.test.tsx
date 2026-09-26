/**
 * ReaderAffordances.test.tsx — reading-global SPR-02 proofs, caller side:
 *
 *   1. DistillView: a node WITH source_document_id renders the quiet "open
 *      in reader" action — activation calls openWindow with the stable
 *      per-document id + the research origin payload; a node WITHOUT one
 *      renders the same inert "no source on record" as always (no dead
 *      affordance).
 *   2. Write's BlockRepository: a hit with source identity offers the
 *      action; activation opens (or focuses) the reader window with the
 *      write origin ({ from: "write", id: deliverableId }).
 *   3. The focus invariant end-to-end: the SAME document opened from
 *      Research (DistillView), then Write (BlockRepository), then DRW
 *      evidence (its exact openWindow call shape) — exactly ONE reader
 *      window exists and each activation focused it (windowsStore state).
 *
 * The origin CONSUMPTION proofs live beside the island harness
 * (Reading/island/originPrefill.test.tsx).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactElement } from "react";

import type { DistilledNode } from "../../lib/api";

const { getDistillationMock, apiFetchMock } = vi.hoisted(() => ({
  getDistillationMock: vi.fn(),
  apiFetchMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    getDistillation: getDistillationMock,
    apiFetch: (i: unknown, init?: unknown) => apiFetchMock(i, init),
  };
});

import DistillView from "./DistillView";
import BlockRepository from "../Write/BlockRepository";
import { openWindow, readerWindowId } from "../../components/windows/openWindow";
import { useWindows } from "../../workspace/windowsStore";

function insight(node_id: string, text: string, source_document_id: string | null): DistilledNode {
  return {
    node_id,
    kind: "insight",
    text,
    confidence: null,
    source_document_id,
    refinement_count: 0,
    escalated: false,
    reserved_child_investigation_id: null,
  };
}

function hit(node_id: string, label: string, document_id: string | null) {
  return {
    node_id,
    label,
    node_type: "insight",
    source_tier: 2,
    document_id,
    document_title: document_id ? "The Source Book" : null,
    score: 1,
  };
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function route() {
  apiFetchMock.mockImplementation(async (input: unknown) => {
    const url = String(input);
    if (url.includes("/write/blocks/search")) {
      return jsonResponse({
        hits: [hit("n-1", "a sourced note", "doc-1"), hit("n-2", "a floating note", null)],
      });
    }
    if (url.includes("/write/folders")) {
      return jsonResponse({ folders: [] });
    }
    return jsonResponse({ text: "reply" });
  });
}

function renderWithRouter(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

beforeEach(() => {
  getDistillationMock.mockReset();
  apiFetchMock.mockReset();
  useWindows.getState().reset();
});

afterEach(() => {
  cleanup();
  useWindows.getState().reset();
});

// ── Proof 1: the DistillView grounding line gains the action ──────────────

describe("DistillView: the grounded-source line", () => {
  it("a node WITH a source renders the quiet action — activation opens the reader with the exact id + research origin", async () => {
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [insight("i1", "GPUs gate scale.", "doc-1")],
      questions: [],
    });
    renderWithRouter(<DistillView investigationId="inv-1" />);
    await screen.findByText("GPUs gate scale.");

    fireEvent.click(screen.getByRole("button", { name: "open in reader" }));

    const state = useWindows.getState();
    const id = readerWindowId("doc-1");
    expect(state.order).toEqual([id]);
    expect(state.focusedId).toBe(id);
    expect(state.windows[id].kind).toBe("reader");
    expect(state.windows[id].payload).toEqual({
      documentId: "doc-1",
      origin: { from: "research", id: "inv-1" },
    });
  });

  it("a node WITHOUT a source renders the same inert line as always — no dead affordance", async () => {
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [insight("i2", "An ungrounded claim.", null)],
      questions: [],
    });
    renderWithRouter(<DistillView investigationId="inv-1" />);
    await screen.findByText("An ungrounded claim.");
    expect(screen.getByText("no source on record")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "open in reader" })).toBeNull();
    expect(useWindows.getState().order).toHaveLength(0);
  });
});

// ── Proof 2: the Write repository surface ─────────────────────────────────

describe("BlockRepository: a hit with source identity", () => {
  it("offers the action; activation opens the reader with the write origin", async () => {
    route();
    renderWithRouter(<BlockRepository onAdd={() => {}} deliverableId="del-1" />);
    await screen.findByText("a sourced note");

    const buttons = screen.getAllByRole("button", { name: "read ↗" });
    expect(buttons).toHaveLength(1); // the sourceless hit offers NOTHING
    fireEvent.click(buttons[0]);

    const state = useWindows.getState();
    const id = readerWindowId("doc-1");
    expect(state.order).toEqual([id]);
    expect(state.windows[id].payload).toEqual({
      documentId: "doc-1",
      origin: { from: "write", id: "del-1" },
    });
  });

  it("without a deliverable in context the action opens the reader with NO origin (lawful — nothing changes)", async () => {
    route();
    renderWithRouter(<BlockRepository onAdd={() => {}} />);
    await screen.findByText("a sourced note");
    fireEvent.click(screen.getByRole("button", { name: "read ↗" }));
    const id = readerWindowId("doc-1");
    expect(useWindows.getState().windows[id].payload).toEqual({ documentId: "doc-1" });
  });
});

// ── Proof 3: the focus invariant across the three caller paths ────────────

describe("one reader per document, from every caller", () => {
  it("Research → Write → DRW evidence on the SAME document: one window, focused each time", async () => {
    route();
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [insight("i1", "GPUs gate scale.", "doc-1")],
      questions: [],
    });
    renderWithRouter(
      <>
        <DistillView investigationId="inv-1" />
        <BlockRepository onAdd={() => {}} deliverableId="del-1" />
      </>,
    );
    await screen.findByText("GPUs gate scale.");
    await screen.findByText("a sourced note");
    const id = readerWindowId("doc-1");

    // From Research.
    fireEvent.click(screen.getByRole("button", { name: "open in reader" }));
    expect(useWindows.getState().order).toEqual([id]);
    expect(useWindows.getState().focusedId).toBe(id);
    expect(useWindows.getState().windows[id].payload.origin).toEqual({
      from: "research",
      id: "inv-1",
    });

    // From Write — the same window, refocused, never duplicated.
    fireEvent.click(screen.getByRole("button", { name: "read ↗" }));
    expect(useWindows.getState().order).toEqual([id]);
    expect(useWindows.getState().focusedId).toBe(id);

    // From DRW evidence — its exact call shape (the caller is proof-tested
    // in DeepResearchWorkspace.waitArcade.test.tsx).
    openWindow(
      "reader",
      { documentId: "doc-1", origin: { from: "evidence", id: "done-1" } },
      { id: readerWindowId("doc-1"), title: "Research source" },
    );
    expect(useWindows.getState().order).toEqual([id]);
    expect(useWindows.getState().focusedId).toBe(id);
    expect(Object.keys(useWindows.getState().windows)).toHaveLength(1);
  });
});
