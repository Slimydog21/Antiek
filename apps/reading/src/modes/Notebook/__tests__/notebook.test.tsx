// SPR-08 / M8 — Per-document notebook surface tests.
//
// Three scopes, matching the sprint HTML acceptance criteria:
//
// 1. Block dispatch: each of the 6 block types renders without
//    throwing. Asserts the M4 "each of 6 block types has a TipTap
//    node-view" criterion at the JSX level (full TipTap install is
//    the operator's near-term task — see SPR-08 handoff).
//
// 2. Demote round-trip in DemoteZone: the zone hides when empty,
//    shows N when there are demoted blocks, expands on click, and
//    fires onDemote(blockId, false) on restore. The persistence
//    layer's demote round-trip is covered separately in
//    services/notebooks/tests/test_auto_populate.py.
//
// 3. No "+ new block": rg the rendered DOM for any "+ new block"
//    or "+ block" or "create block" string. The acceptance gate.

import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";

import { renderBlock } from "../blocks";
import DemoteZone from "../DemoteZone";
import type { PerDocNotebookBlock } from "../../../../api/notebooks/by-doc";

afterEach(() => {
  cleanup();
});


function makeBlock(
  overrides: Partial<PerDocNotebookBlock> & { block_type: string },
): PerDocNotebookBlock {
  // ``block_type`` is widened to string for the unknown-type fallback
  // case below; the surface type narrows to the closed set, so we
  // assert through ``unknown`` to satisfy the compiler while still
  // letting the dispatch test exercise the UnknownBlock fallback.
  const base: PerDocNotebookBlock = {
    block_id: `blk-${overrides.block_type}-1`,
    notebook_id: "nbk-test",
    block_type:
      overrides.block_type as PerDocNotebookBlock["block_type"],
    source_event_ids: ["evt-source-1"],
    document_id: "doc-test",
    content_json: {},
    position: 1.0,
    demoted_at: null,
    edited_at: null,
    created_at: "2026-05-21T10:00:00Z",
  };
  // Apply overrides excluding block_type (already in base) to avoid
  // the TS2783 duplicate-key warning.
  const { block_type: _ignored, ...rest } = overrides;
  void _ignored;
  return { ...base, ...rest };
}


describe("M4 — block dispatch renders each closed-set type", () => {
  const blockTypes = [
    "highlight_card",
    "voice_block",
    "ai_qa",
    "cite_link",
    "cross_doc_jump",
    "prose",
  ];

  for (const type of blockTypes) {
    it(`renders block_type=${type} without throwing`, () => {
      const block = makeBlock({ block_type: type as PerDocNotebookBlock["block_type"] });
      render(renderBlock({ block }));
      // The shell stamps data-block-type as a hook for E2E inspection.
      const section = document.querySelector(`[data-block-type="${type}"]`);
      expect(section).toBeTruthy();
    });
  }

  it("falls back to UnknownBlock for non-closed-set types (data-block-type stamped)", () => {
    // Deliberately violates the closed-set narrowing to exercise the
    // dispatch fallback; the cast is the test author's responsibility,
    // not a real surface.
    const block = makeBlock({
      block_type: "imaginary_block" as unknown as PerDocNotebookBlock["block_type"],
    });
    render(renderBlock({ block }));
    const section = document.querySelector(
      '[data-block-type="imaginary_block"]',
    );
    expect(section).toBeTruthy();
    expect(section?.textContent).toMatch(/Unknown block type/);
  });
});


describe("M5 — demote round-trip", () => {
  it("returns null when there are no demoted blocks", () => {
    const { container } = render(
      <DemoteZone blocks={[]} onDemote={() => undefined} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows the demoted count and expands on click", () => {
    const demoted: PerDocNotebookBlock[] = [
      makeBlock({
        block_id: "blk-d-1",
        block_type: "highlight_card",
        demoted_at: "2026-05-21T11:00:00Z",
      }),
      makeBlock({
        block_id: "blk-d-2",
        block_type: "voice_block",
        demoted_at: "2026-05-21T11:01:00Z",
      }),
    ];
    render(<DemoteZone blocks={demoted} onDemote={() => undefined} />);
    const toggle = screen.getByTestId("demote-zone-toggle");
    expect(toggle.textContent).toMatch(/Demoted \(2\)/);
    // Children collapsed by default.
    expect(
      document.querySelector('[data-block-id="blk-d-1"]'),
    ).toBeFalsy();
    fireEvent.click(toggle);
    expect(
      document.querySelector('[data-block-id="blk-d-1"]'),
    ).toBeTruthy();
    expect(
      document.querySelector('[data-block-id="blk-d-2"]'),
    ).toBeTruthy();
  });

  it("clicking restore on a demoted block fires onDemote(blockId, false)", () => {
    const demoted = makeBlock({
      block_id: "blk-d-restore",
      block_type: "highlight_card",
      demoted_at: "2026-05-21T11:00:00Z",
    });
    const onDemote = vi.fn();
    render(<DemoteZone blocks={[demoted]} onDemote={onDemote} />);
    fireEvent.click(screen.getByTestId("demote-zone-toggle"));
    const restoreBtn = screen.getByTestId(
      `demote-button-${demoted.block_id}`,
    );
    expect(restoreBtn.textContent).toMatch(/restore/);
    fireEvent.click(restoreBtn);
    expect(onDemote).toHaveBeenCalledWith(demoted.block_id, false);
  });
});


describe("M5 — no '+ new block' affordance in any block component", () => {
  /** The acceptance gate. The block components must never render a
   * "+ new block" / "create block" affordance. We render one of each
   * block type AND the DemoteZone with demoted blocks AND a fully
   * editable shell, then scan the resulting DOM. */
  it("no rendered block surface contains '+ new block' or 'create block'", () => {
    const blocks: PerDocNotebookBlock[] = [
      makeBlock({ block_type: "highlight_card", block_id: "b-h" }),
      makeBlock({ block_type: "voice_block", block_id: "b-v" }),
      makeBlock({ block_type: "ai_qa", block_id: "b-a" }),
      makeBlock({ block_type: "cite_link", block_id: "b-c" }),
      makeBlock({ block_type: "cross_doc_jump", block_id: "b-x" }),
      makeBlock({ block_type: "prose", block_id: "b-p" }),
    ];
    const { container } = render(
      <div>
        {blocks.map((b) =>
          renderBlock({
            block: b,
            onEditFraming: () => undefined,
            onDemote: () => undefined,
          }),
        )}
        <DemoteZone
          blocks={[
            makeBlock({
              block_type: "highlight_card",
              block_id: "b-h-d",
              demoted_at: "2026-05-21T11:00:00Z",
            }),
          ]}
          onDemote={() => undefined}
        />
      </div>,
    );
    const text = container.textContent || "";
    expect(text.toLowerCase()).not.toMatch(/\+ new block/);
    expect(text.toLowerCase()).not.toMatch(/create block/);
    expect(text.toLowerCase()).not.toMatch(/new block/);
  });
});


describe("M4 — operator framing surfaces an editable textarea", () => {
  it("renders the framing textarea when onEditFraming is provided", () => {
    const block = makeBlock({ block_type: "highlight_card" });
    render(
      renderBlock({
        block,
        onEditFraming: () => undefined,
      }),
    );
    expect(screen.getByTestId(`framing-textarea-${block.block_id}`)).toBeTruthy();
  });

  it("does NOT render a textarea when onEditFraming is absent (read-only)", () => {
    const block = makeBlock({ block_type: "highlight_card" });
    render(renderBlock({ block }));
    expect(
      document.querySelector(`[data-testid="framing-textarea-${block.block_id}"]`),
    ).toBeFalsy();
  });

  it("fires onEditFraming on blur with the typed value", () => {
    const block = makeBlock({ block_type: "highlight_card" });
    const onEditFraming = vi.fn();
    render(renderBlock({ block, onEditFraming }));
    const textarea = screen.getByTestId(
      `framing-textarea-${block.block_id}`,
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "operator notes here" } });
    fireEvent.blur(textarea);
    expect(onEditFraming).toHaveBeenCalledWith(
      block.block_id,
      "operator notes here",
    );
  });
});


describe("M4 — Prose orphan guard", () => {
  it("renders ORPHAN warning when a prose block has no source events", () => {
    const orphan = makeBlock({
      block_type: "prose",
      source_event_ids: [],
    });
    render(renderBlock({ block: orphan }));
    const section = document.querySelector('[data-block-type="prose"]');
    expect(section?.textContent).toMatch(/Orphan prose block/);
  });
});
