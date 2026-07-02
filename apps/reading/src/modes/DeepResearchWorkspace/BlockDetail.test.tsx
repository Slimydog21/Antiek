/**
 * BlockDetail.test.tsx — SPR-04 M1: prove the SECOND live FloatMenu host works.
 *
 * BlockDetail is the second host that mounts the SHARED FloatMenu (the first is
 * the Research synthesis surface via HighlightToolbar). The verifier-critic
 * flagged that this host was type-checked but never EXERCISED — so this suite
 * MOUNTS BlockDetail, drives a real text selection inside its scope, and asserts:
 *   - a selection inside the block opens the SAME four-action FloatMenu;
 *   - the RICHER-provenance path is covered: a NOTE on a block-detail selection
 *     chains to the node's own `source_document_id` + `chunk_id`
 *     (BlockDetail.resolveProvenance), so the persisted marginalia.noted
 *     carries the claim→chunk→document §9 chain.
 *
 * Selection in jsdom follows the FloatMenu.test.tsx pattern: a real Range over a
 * text node inside the scope + a spied getBoundingClientRect + a mocked
 * getSelection, fired via `selectionchange`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { DistilledNode } from "../../lib/api";

// Mock the api boundary — capture the NOTE write (postTypedEvent). Same shape
// FloatMenu.test.tsx uses, mocked at the api boundary only.
const { navigateMock, recordSpawnMock, startInvestigationMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  recordSpawnMock: vi.fn(),
  startInvestigationMock: vi.fn(),
}));

const postTypedEventMock = vi.fn((_envelope: unknown) =>
  Promise.resolve({ event_id: "ev-note-1", action_type: "marginalia.noted" }),
);

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    postTypedEvent: (envelope: unknown) => postTypedEventMock(envelope),
    startInvestigation: startInvestigationMock,
  };
});

vi.mock("../../hooks/useInvestigationTree", () => ({
  recordSpawnRelationship: recordSpawnMock,
}));

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

import BlockDetail from "./BlockDetail";

// ── jsdom selection helper (same pattern as FloatMenu.test.tsx) ──────────────

/** Select `text` inside `scope`, give the range a rect, and fire
 *  `selectionchange`. Returns the range. */
function selectTextIn(
  scope: HTMLElement,
  text: string,
  rect = { top: 200, left: 100, width: 80, height: 18 },
): Range {
  const node = scope.firstChild as Text;
  const range = document.createRange();
  range.setStart(node, 0);
  range.setEnd(node, node.textContent?.length ?? text.length);
  range.getBoundingClientRect = () =>
    ({
      ...rect,
      right: rect.left + rect.width,
      bottom: rect.top + rect.height,
      x: rect.left,
      y: rect.top,
      toJSON() {
        return rect;
      },
    }) as DOMRect;
  vi.spyOn(window, "getSelection").mockReturnValue({
    rangeCount: 1,
    getRangeAt: () => range,
    toString: () => text,
    removeAllRanges: () => {},
  } as unknown as Selection);
  act(() => {
    document.dispatchEvent(new Event("selectionchange"));
  });
  return range;
}

function insightNode(extra: Partial<DistilledNode> = {}): DistilledNode {
  return {
    node_id: "i1",
    kind: "insight",
    text: "a grounded insight worth selecting and noting",
    confidence: "high",
    source_document_id: "doc-block-9",
    chunk_id: "chunk-block-9",
    refinement_count: 0,
    escalated: false,
    reserved_child_investigation_id: null,
    ...extra,
  };
}

function renderDetail(node: DistilledNode) {
  return render(
    <MemoryRouter>
      <BlockDetail node={node} investigationId="inv-block" onClose={() => {}} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  postTypedEventMock.mockClear();
  navigateMock.mockReset();
  recordSpawnMock.mockReset();
  startInvestigationMock.mockReset();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("BlockDetail — the SECOND live FloatMenu host (M1)", () => {
  it("a text selection inside the block detail opens the SAME four-action FloatMenu", () => {
    renderDetail(insightNode());
    // The scope is the node-text container; nothing is open until a selection.
    expect(screen.queryByRole("menu")).toBeNull();
    // Select inside the node-text scope (the block's own rendered text).
    const scope = screen.getByText(
      "a grounded insight worth selecting and noting",
    );
    selectTextIn(scope, "a grounded insight");
    // The SAME shared FloatMenu opens — all four actions present.
    expect(screen.getByRole("menu")).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Note" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Dialogue" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Search" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Deep-research" })).toBeTruthy();
  });

  it("a NOTE on a block-detail selection chains to the node's source document and chunk (richer provenance §9)", async () => {
    renderDetail(insightNode({ source_document_id: "doc-block-9", chunk_id: "chunk-block-9" }));
    const scope = screen.getByText(
      "a grounded insight worth selecting and noting",
    );
    selectTextIn(scope, "a grounded insight");
    fireEvent.click(screen.getByRole("menuitem", { name: "Note" }));
    const textarea = screen.getByPlaceholderText("Type a note, or speak it…");
    fireEvent.change(textarea, { target: { value: "this block matters" } });
    await act(async () => {
      fireEvent.click(screen.getByText("Save note"));
    });
    expect(postTypedEventMock).toHaveBeenCalledTimes(1);
    const env = postTypedEventMock.mock.calls[0][0] as {
      document_id?: string;
      payload: { action_type: string; source_kind: string; chunk_id: string | null };
    };
    // BlockDetail.resolveProvenance grounds the note in the node's OWN source
    // document and chunk — the richer provenance this host adds over the
    // synthesis host.
    expect(env.document_id).toBe("doc-block-9");
    expect(env.payload.chunk_id).toBe("chunk-block-9");
    expect(env.payload.action_type).toBe("marginalia.noted");
    // §9 — a marginalia note stays user-sourced (never a model label).
    expect(env.payload.source_kind).toBe("user");
  });

  it("records null chunk provenance when the node has no chunk_id", async () => {
    const node = insightNode({ source_document_id: "doc-block-9" });
    delete node.chunk_id;
    renderDetail(node);
    const scope = screen.getByText(
      "a grounded insight worth selecting and noting",
    );
    selectTextIn(scope, "a grounded insight");
    fireEvent.click(screen.getByRole("menuitem", { name: "Note" }));
    const textarea = screen.getByPlaceholderText("Type a note, or speak it…");
    fireEvent.change(textarea, { target: { value: "this block has no chunk" } });
    await act(async () => {
      fireEvent.click(screen.getByText("Save note"));
    });
    const env = postTypedEventMock.mock.calls[0][0] as {
      document_id?: string;
      payload: { chunk_id: string | null };
    };
    expect(env.document_id).toBe("doc-block-9");
    expect(env.payload.chunk_id).toBeNull();
  });

  it("trims child investigation ids before recording a deep-research spawn", async () => {
    startInvestigationMock.mockResolvedValue({
      investigation_id: " inv-child ",
      status: "in_progress",
      start_event_id: "e1",
    });
    renderDetail(insightNode());
    const scope = screen.getByText(
      "a grounded insight worth selecting and noting",
    );
    selectTextIn(scope, "a grounded insight");

    fireEvent.click(screen.getByRole("menuitem", { name: "Deep-research" }));

    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(1));
    expect(recordSpawnMock).toHaveBeenCalledWith("inv-child", "inv-block");
    expect(navigateMock).toHaveBeenCalledWith("/inv/inv-child");
  });

  it("surfaces malformed deep-research child ids instead of linking or navigating", async () => {
    startInvestigationMock.mockResolvedValue({
      investigation_id: " ",
      status: "in_progress",
      start_event_id: "e1",
    });
    renderDetail(insightNode());
    const scope = screen.getByText(
      "a grounded insight worth selecting and noting",
    );
    selectTextIn(scope, "a grounded insight");

    fireEvent.click(screen.getByRole("menuitem", { name: "Deep-research" }));

    expect((await screen.findByRole("alert")).textContent).toMatch(
      /investigation_id must be a non-empty string/i,
    );
    expect(recordSpawnMock).not.toHaveBeenCalled();
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
