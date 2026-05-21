// SPR-07 M6 — Gutter behavior-event funnel + render tests.
//
// Covers:
//   - M2: pills appear after fetch resolves; up to 3.
//   - M3: hover shows preview.
//   - M6: surfaced + clicked + dismissed events fire correctly per
//     scenario (the two scenarios spelled out in the spec's M6
//     acceptance criteria).
//
// We mock ``fetchCrossDocLinks`` via the Gutter's ``fetchLinks`` prop
// injection (the production fetcher hits the network; tests use a
// deterministic stub). Behavior-event emission is observed by
// replacing the no-op-on-wire ``emitBehaviorEvent`` with a capturing
// spy — the existing module exports a function we can vi.spyOn.
//
// The cite-jump navigation (window.location.href assignment) is
// stubbed via defineProperty so the test doesn't actually navigate
// out of the jsdom page.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";

import type { CrossDocLink } from "../../../../../api/cross_doc/links";
import * as behaviorEvents from "../../../../lib/behaviorEvents";
import { _resetUserSettingsForTest } from "../../../../settings/userSettings";

import Gutter, { PILL_COUNT_LIMIT, type ActiveHighlight } from "../Gutter";

function makeLink(overrides: Partial<CrossDocLink> = {}): CrossDocLink {
  return {
    chunk_id: "chunk-abc",
    doc_title: "Antiek Substrate Notes",
    document_id: "doc-target",
    page: 4,
    snippet: "A short snippet of the connected passage.",
    score: 0.72,
    source: "similarity",
    source_tier: 2,
    ...overrides,
  };
}

function makeHighlight(overrides: Partial<ActiveHighlight> = {}): ActiveHighlight {
  return {
    highlightId: "h-1",
    documentId: "doc-source",
    page: 1,
    bbox: [10, 20, 100, 40],
    topPx: 120,
    selectedText: "selected passage",
    ...overrides,
  };
}

describe("Gutter — render + pills (M2)", () => {
  beforeEach(() => {
    _resetUserSettingsForTest();
  });
  afterEach(() => {
    cleanup();
  });

  it("renders up to PILL_COUNT_LIMIT pills per highlight", async () => {
    const fetchLinks = vi.fn().mockResolvedValue([
      makeLink({ chunk_id: "c-1", doc_title: "Doc One" }),
      makeLink({ chunk_id: "c-2", doc_title: "Doc Two", document_id: "doc-t2" }),
      makeLink({ chunk_id: "c-3", doc_title: "Doc Three", document_id: "doc-t3" }),
      // 4th would exceed the limit — must not render.
      makeLink({ chunk_id: "c-4", doc_title: "Doc Four", document_id: "doc-t4" }),
    ]);
    render(<Gutter highlights={[makeHighlight()]} fetchLinks={fetchLinks} />);
    await waitFor(() => {
      expect(screen.getAllByTestId("gutter-pill")).toHaveLength(PILL_COUNT_LIMIT);
    });
  });

  it("renders no pills when fetcher returns []", async () => {
    const fetchLinks = vi.fn().mockResolvedValue([]);
    render(<Gutter highlights={[makeHighlight()]} fetchLinks={fetchLinks} />);
    await waitFor(() => expect(fetchLinks).toHaveBeenCalled());
    // No pills, no preview.
    expect(screen.queryAllByTestId("gutter-pill")).toHaveLength(0);
  });

  it("calls the fetcher with the highlight and topK=3", async () => {
    const fetchLinks = vi.fn().mockResolvedValue([makeLink()]);
    const h = makeHighlight({ selectedText: "specific text" });
    render(<Gutter highlights={[h]} fetchLinks={fetchLinks} />);
    await waitFor(() => expect(fetchLinks).toHaveBeenCalled());
    expect(fetchLinks).toHaveBeenCalledWith(
      expect.objectContaining({
        document_id: h.documentId,
        selected_text: "specific text",
      }),
      expect.objectContaining({
        topK: PILL_COUNT_LIMIT,
        includePublicGraph: false,
      }),
    );
  });
});

describe("Gutter — hover preview (M3)", () => {
  beforeEach(() => {
    _resetUserSettingsForTest();
  });
  afterEach(() => {
    cleanup();
  });

  it("shows CitePreview on pill hover", async () => {
    const fetchLinks = vi
      .fn()
      .mockResolvedValue([makeLink({ doc_title: "Hoverable Doc" })]);
    render(<Gutter highlights={[makeHighlight()]} fetchLinks={fetchLinks} />);
    const pill = await screen.findByTestId("gutter-pill");
    fireEvent.mouseEnter(pill);
    const preview = await screen.findByTestId("cite-preview");
    expect(within(preview).getByText(/Hoverable Doc/)).toBeTruthy();
    // Preview disappears on mouseleave.
    fireEvent.mouseLeave(pill);
    await waitFor(() => {
      expect(screen.queryByTestId("cite-preview")).toBeNull();
    });
  });
});

describe("Gutter — behavior-event funnel (M6)", () => {
  // Stub window.location.href so the click test doesn't navigate.
  let originalLocation: Location;

  beforeEach(() => {
    _resetUserSettingsForTest();
    originalLocation = window.location;
    // Replace href with a settable property captured by tests.
    delete (window as { location?: Location }).location;
    (window as { location: { href: string } }).location = { href: "" };
  });

  afterEach(() => {
    cleanup();
    (window as { location: Location }).location = originalLocation;
    vi.restoreAllMocks();
  });

  it("scenario A: highlight → hover pill → click — 1 surfaced + 1 clicked + 0 dismissed", async () => {
    const emitSpy = vi.spyOn(behaviorEvents, "emitBehaviorEvent");
    const fetchLinks = vi
      .fn()
      .mockResolvedValue([makeLink({ chunk_id: "c-target" })]);
    const { rerender } = render(
      <Gutter highlights={[makeHighlight()]} fetchLinks={fetchLinks} />,
    );

    // Wait for surfaced event (one emission, AFTER fetch resolves).
    await waitFor(() => {
      expect(
        emitSpy.mock.calls.find(
          ([opts]) => opts.eventType === "cross_doc_link_surfaced",
        ),
      ).toBeTruthy();
    });
    const surfacedCalls = emitSpy.mock.calls.filter(
      ([opts]) => opts.eventType === "cross_doc_link_surfaced",
    );
    expect(surfacedCalls).toHaveLength(1);

    // Hover (no event in taxonomy — UI-only).
    const pill = await screen.findByTestId("gutter-pill");
    fireEvent.mouseEnter(pill);
    await screen.findByTestId("cite-preview");

    // Click Open.
    fireEvent.click(screen.getByTestId("cite-preview-open"));

    const clickedCalls = emitSpy.mock.calls.filter(
      ([opts]) => opts.eventType === "cross_doc_link_clicked",
    );
    expect(clickedCalls).toHaveLength(1);

    // Remove the highlight (e.g. selection cleared) AFTER click.
    rerender(<Gutter highlights={[]} fetchLinks={fetchLinks} />);
    await waitFor(() => {
      // No dismissal because the highlight was clicked through.
      const dismissedCalls = emitSpy.mock.calls.filter(
        ([opts]) => opts.eventType === "cross_doc_link_dismissed",
      );
      expect(dismissedCalls).toHaveLength(0);
    });
  });

  it("scenario B: highlight → clear without click — 1 surfaced + 1 dismissed", async () => {
    const emitSpy = vi.spyOn(behaviorEvents, "emitBehaviorEvent");
    const fetchLinks = vi
      .fn()
      .mockResolvedValue([makeLink({ chunk_id: "c-target" })]);
    const { rerender } = render(
      <Gutter highlights={[makeHighlight()]} fetchLinks={fetchLinks} />,
    );

    // Wait for surfaced.
    await waitFor(() => {
      const sc = emitSpy.mock.calls.filter(
        ([opts]) => opts.eventType === "cross_doc_link_surfaced",
      );
      expect(sc).toHaveLength(1);
    });

    // Clear the highlight without clicking.
    rerender(<Gutter highlights={[]} fetchLinks={fetchLinks} />);

    await waitFor(() => {
      const dc = emitSpy.mock.calls.filter(
        ([opts]) => opts.eventType === "cross_doc_link_dismissed",
      );
      expect(dc).toHaveLength(1);
    });
    expect(
      emitSpy.mock.calls.filter(
        ([opts]) => opts.eventType === "cross_doc_link_clicked",
      ),
    ).toHaveLength(0);
  });

  it("surfaced event fires ONCE per highlight even with 3 pills", async () => {
    const emitSpy = vi.spyOn(behaviorEvents, "emitBehaviorEvent");
    const fetchLinks = vi.fn().mockResolvedValue([
      makeLink({ chunk_id: "c-1" }),
      makeLink({ chunk_id: "c-2", document_id: "doc-t2" }),
      makeLink({ chunk_id: "c-3", document_id: "doc-t3" }),
    ]);
    render(<Gutter highlights={[makeHighlight()]} fetchLinks={fetchLinks} />);
    await waitFor(() => {
      const sc = emitSpy.mock.calls.filter(
        ([opts]) => opts.eventType === "cross_doc_link_surfaced",
      );
      expect(sc).toHaveLength(1);
    });
  });
});
