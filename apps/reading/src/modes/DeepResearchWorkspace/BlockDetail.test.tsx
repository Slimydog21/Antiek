/**
 * BlockDetail.test.tsx — SPR-04 M1: prove the SECOND live FloatMenu host works.
 *
 * BlockDetail is the second host that mounts the SHARED FloatMenu (the first is
 * the Research synthesis surface via HighlightToolbar). The verifier-critic
 * flagged that this host was type-checked but never EXERCISED — so this suite
 * MOUNTS BlockDetail, drives a real text selection inside its scope, and asserts:
 *   - a selection inside the block opens the SAME four-action FloatMenu;
 *   - the RICHER-provenance path is covered: a NOTE on a block-detail selection
 *     chains to the node's own `source_document_id` (BlockDetail.resolveProvenance),
 *     so the persisted marginalia.noted carries that document_id (§9 chain).
 *
 * Selection in jsdom follows the FloatMenu.test.tsx pattern: a real Range over a
 * text node inside the scope + a spied getBoundingClientRect + a mocked
 * getSelection, fired via `selectionchange`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { DistilledNode } from "../../lib/api";

// Mock the api boundary — capture the NOTE write (postTypedEvent). Same shape
// FloatMenu.test.tsx uses, mocked at the api boundary only.
const postTypedEventMock = vi.fn((_envelope: unknown) =>
  Promise.resolve({ event_id: "ev-note-1", action_type: "marginalia.noted" }),
);
const launchFloatingDeepResearch = vi.fn();
const startInvestigation = vi.fn();
const fetchDepthTiers = vi.hoisted(() =>
  vi.fn(async () => ({
    active_depth_tier: null as string | null,
    active_preset: null,
    tiers: [],
  })),
);

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    postTypedEvent: (envelope: unknown) => postTypedEventMock(envelope),
    startInvestigation: (...args: unknown[]) => startInvestigation(...args),
  };
});

vi.mock("../../api/settings", () => ({
  fetchDepthTiers: (...args: unknown[]) => fetchDepthTiers(...args),
}));

vi.mock("../Reading/launchFloatingDeepResearch", () => ({
  launchFloatingDeepResearch: (...args: unknown[]) =>
    launchFloatingDeepResearch(...args),
}));

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
  launchFloatingDeepResearch.mockReset();
  startInvestigation.mockReset();
  fetchDepthTiers.mockReset().mockResolvedValue({
    active_depth_tier: null,
    active_preset: null,
    tiers: [],
  });
  launchFloatingDeepResearch.mockResolvedValue({
    session_id: "fsess_b",
    spawn_id: "spn_b",
    investigation_id: "inv_b",
    parent_asset_id: "doc-block-9",
    window_id: "wdr_b",
    view_format: "html",
    view_mode: "floating",
    status: "reserved",
    model_id: null,
    research_tier: "deep",
  });
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
    // The SAME shared FloatMenu opens — all four actions present + full (fe/fh).
    expect(screen.getByRole("menu")).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Note" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Dialogue" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Search" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Deep-research" })).toBeTruthy();
    expect(
      screen.getByRole("menuitem", { name: "Deep-research full" }),
    ).toBeTruthy();
  });

  it("Deep-research launches floating window via launchFloatingDeepResearch (fh)", async () => {
    renderDetail(insightNode());
    const scope = screen.getByText(
      "a grounded insight worth selecting and noting",
    );
    selectTextIn(scope, "a grounded insight");
    await act(async () => {
      fireEvent.click(screen.getByRole("menuitem", { name: "Deep-research" }));
    });
    expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
      expect.objectContaining({
        asset_id: "doc-block-9",
        selection_text: "a grounded insight",
        view_mode: "floating",
        research_tier: "deep",
      }),
    );
    expect(startInvestigation).not.toHaveBeenCalled();
  });

  it("Deep-research forwards Settings wrestle research_tier (jj)", async () => {
    fetchDepthTiers.mockResolvedValue({
      active_depth_tier: "wrestle",
      active_preset: null,
      tiers: [],
    });
    renderDetail(insightNode());
    // Let Settings prefill settle before clicking Deep-research.
    await act(async () => {
      await Promise.resolve();
    });
    const scope = screen.getByText(
      "a grounded insight worth selecting and noting",
    );
    selectTextIn(scope, "a grounded insight");
    await act(async () => {
      fireEvent.click(screen.getByRole("menuitem", { name: "Deep-research" }));
    });
    expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
      expect.objectContaining({
        asset_id: "doc-block-9",
        research_tier: "wrestle",
        view_mode: "floating",
      }),
    );
  });

  it("Deep-research full launches full window mode (fh)", async () => {
    renderDetail(insightNode());
    const scope = screen.getByText(
      "a grounded insight worth selecting and noting",
    );
    selectTextIn(scope, "a grounded insight");
    await act(async () => {
      fireEvent.click(
        screen.getByRole("menuitem", { name: "Deep-research full" }),
      );
    });
    expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
      expect.objectContaining({
        asset_id: "doc-block-9",
        view_mode: "full",
      }),
    );
  });

  it("a NOTE on a block-detail selection chains to the node's source_document_id (richer provenance §9)", async () => {
    renderDetail(insightNode({ source_document_id: "doc-block-9" }));
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
      payload: { action_type: string; source_kind: string };
    };
    // BlockDetail.resolveProvenance grounds the note in the node's OWN source
    // document — the richer provenance this host adds over the synthesis host.
    expect(env.document_id).toBe("doc-block-9");
    expect(env.payload.action_type).toBe("marginalia.noted");
    // §9 — a marginalia note stays user-sourced (never a model label).
    expect(env.payload.source_kind).toBe("user");
  });
});
