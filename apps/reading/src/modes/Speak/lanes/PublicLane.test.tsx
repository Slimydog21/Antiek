/**
 * PublicLane.test — the public lane, honestly locked & searchable (SPR-03).
 *
 * Load-bearing claims this pins:
 *   - M1: the search box filters the feed by name; clearing restores it; the
 *     loading, honest-empty, and empty-search states each render.
 *   - M2: the G7 locked panel renders the canonical GATE_PHRASES copy VERBATIM
 *     (static, future-tense) — there is NO live G7 read to mock (getEconomics
 *     carries no ecosystem signal), so for G7 this is a content assertion, not
 *     a branch on economics.
 *   - M3: the CTA renders a USABLE action — a real /speak/:id link (the
 *     operator's own public-intent project), never /login and never a dead end;
 *     and it is honestly framed that open contribution by others is not live.
 *   - M4: the explainer is honest-tense and carries no per-second ad model, AND
 *     its G2/G3 publishing + payout lines reflect LIVE gate state read via
 *     `getEconomics` — both the gated branch and the open branch are asserted.
 *   - M5: a feed item is labelled intended-public, never "published".
 *
 * The G2/G3 read is LIVE (Rigor-3): PublicLane fetches `getEconomics(feed[0].id)`
 * once when the feed is non-empty (G2/G3 are global env-flag states surfaced
 * per-project, so any project answers correctly). We exercise BOTH branches by
 * mocking getEconomics gated vs open. G7 stays static (no FE read exists).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// vi.hoisted + vi.mock the data edge, per the SPR-03 harness. PublicLane reads
// getEconomics LIVE (G2/G3); listPublicFeed is mocked so the lane's
// type/value imports resolve cleanly under the spec's stated harness.
const { getEconomicsMock, listPublicFeedMock } = vi.hoisted(() => ({
  getEconomicsMock: vi.fn(),
  listPublicFeedMock: vi.fn(),
}));

vi.mock("../../../lib/speakApi", async (orig) => ({
  ...(await orig<typeof import("../../../lib/speakApi")>()),
  getEconomics: getEconomicsMock,
  listPublicFeed: listPublicFeedMock,
}));

import PublicLane from "./PublicLane";
import type { EconomicsView, FeedItem } from "../../../lib/speakApi";
import { GATE_PHRASES, PUBLIC_LANE_LABELS } from "../../../lib/speakVocab";

// A full EconomicsView with the two G2/G3 flags overridable per test. The
// non-gate fields don't affect the explainer branch; they just satisfy the type.
function economics(over: Partial<EconomicsView>): EconomicsView {
  return {
    splitApplies: false,
    creatorCarriesCost: false,
    publicPublishingAllowed: false,
    publicPublishingReason: "",
    disbursementAllowed: false,
    disbursementReason: "",
    ...over,
  };
}

// Deny-by-default for every test that doesn't care about the live read (e.g.
// the empty-feed states never fetch). Tests that assert a branch override this.
beforeEach(() => {
  getEconomicsMock.mockReset().mockResolvedValue(economics({}));
  listPublicFeedMock.mockReset();
});
afterEach(cleanup);

const FEED: FeedItem[] = [
  { id: "p1", name: "Grandma Rosa", voiceCount: 3, readerDocumentId: null },
  { id: "p2", name: "Uncle Theo", voiceCount: 0, readerDocumentId: null },
];

function mount(props: { feedLoading?: boolean; feed?: FeedItem[] } = {}) {
  return render(
    <MemoryRouter>
      <PublicLane feedLoading={props.feedLoading ?? false} feed={props.feed ?? FEED} />
    </MemoryRouter>,
  );
}

describe("PublicLane — searchable feed", () => {
  it("renders every feed item by name", () => {
    mount();
    expect(screen.getByText("Grandma Rosa")).toBeTruthy();
    expect(screen.getByText("Uncle Theo")).toBeTruthy();
  });

  it("links only a servable publication into the HTML reader", () => {
    mount({
      feed: [{ id: "p1", name: "Grandma Rosa", voiceCount: 3, readerDocumentId: "doc-1" }],
    });
    const link = screen.getByRole("link", { name: /read story/i });
    expect(link.getAttribute("href")).toBe("/read/doc-1");
    expect(screen.getByText(/published as a readable story/i)).toBeTruthy();
  });

  it("filters by name and restores the full list when cleared (M1)", () => {
    mount();
    const search = screen.getByLabelText(/search public remembrances/i);

    fireEvent.change(search, { target: { value: "rosa" } });
    expect(screen.getByText("Grandma Rosa")).toBeTruthy();
    expect(screen.queryByText("Uncle Theo")).toBeNull();

    fireEvent.change(search, { target: { value: "" } });
    expect(screen.getByText("Grandma Rosa")).toBeTruthy();
    expect(screen.getByText("Uncle Theo")).toBeTruthy();
  });

  it("shows the honest empty-search state naming the query (M1)", () => {
    mount();
    const search = screen.getByLabelText(/search public remembrances/i);
    fireEvent.change(search, { target: { value: "nobody-here" } });
    expect(screen.getByText(/nothing matches/i)).toBeTruthy();
    expect(screen.getByText(/nobody-here/)).toBeTruthy();
  });

  it("renders the honest loading state (M1)", () => {
    mount({ feedLoading: true, feed: [] });
    expect(screen.getByText(/loading/i)).toBeTruthy();
  });

  it("renders the honest empty state when there are no public remembrances (M1)", () => {
    mount({ feed: [] });
    expect(screen.getByText(/no public remembrances yet/i)).toBeTruthy();
  });
});

describe("PublicLane — the honest G7 locked state (M2)", () => {
  it("renders the canonical GATE_PHRASES.publicEcosystem copy verbatim (static, not a live read)", () => {
    mount();
    // The label AND the future-tense sentence come straight from the vocab —
    // no fabricated live G7 read, no invented endpoint.
    expect(screen.getByText(GATE_PHRASES.publicEcosystem.label)).toBeTruthy();
    expect(
      screen.getAllByText(GATE_PHRASES.publicEcosystem.whenGated).length,
    ).toBeGreaterThan(0);
  });

  it("offers NO close / enable / unlock affordance on the lock", () => {
    mount();
    // No button anywhere claims to open/enable/unlock the gate.
    for (const btn of screen.queryAllByRole("button")) {
      expect(/enable|unlock|activate|open the gate/i.test(btn.textContent ?? "")).toBe(false);
    }
  });
});

describe("PublicLane — the CTA is usable, not a dead end (M3)", () => {
  it("renders an 'Add your memory' action linking to the operator's own /speak/:id (never /login)", () => {
    mount({ feed: [{ id: "p9", name: "Aunt May", voiceCount: 1, readerDocumentId: null }] });
    const cta = screen.getByRole("button", { name: /add your memory/i });
    expect(cta).toBeTruthy();

    // It is wrapped in a real link to the project — a working action for the
    // authed operator, NOT /login and NOT a dead/clickable-but-403 control.
    const links = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(links).toContain("/speak/p9");
    for (const href of links) {
      expect(href).not.toBe("/login");
      expect(href).not.toBeNull();
      expect(href).not.toBe("#");
    }
  });

  it("is honest that open contribution by others is not live", () => {
    mount({ feed: [{ id: "p9", name: "Aunt May", voiceCount: 1, readerDocumentId: null }] });
    expect(screen.getByText(PUBLIC_LANE_LABELS.ctaOperatorOnly)).toBeTruthy();
  });
});

describe("PublicLane — lifecycle & north-star honesty (M4 + M5)", () => {
  it("labels a feed item intended-public and NEVER claims it is published (M5)", () => {
    mount({ feed: [{ id: "p9", name: "Aunt May", voiceCount: 1, readerDocumentId: null }] });
    expect(screen.getByText(PUBLIC_LANE_LABELS.intendedPublic)).toBeTruthy();
    // Nothing in the lane claims a project is "published".
    expect(screen.queryByText(/\bpublished\b/i)).toBeNull();
  });

  it("renders an honest-tense explainer with no per-second / timecode ad model (M4)", () => {
    const { container } = mount();
    expect(screen.getByText(PUBLIC_LANE_LABELS.explainerHeading)).toBeTruthy();
    expect(screen.getByText(PUBLIC_LANE_LABELS.explainerPayoutBasis)).toBeTruthy();
    // The §9.3 Option-B guard: no per-second / timecode ad fiction reaches the DOM.
    expect(/per.second|timecode|mid.?roll|ad seconds?/i.test(container.textContent ?? "")).toBe(false);
  });
});

describe("PublicLane — the G2/G3 explainer lines are read LIVE (M4 / Rigor-3)", () => {
  it("reads getEconomics from the first feed item once (the live probe)", async () => {
    getEconomicsMock.mockResolvedValue(economics({ publicPublishingAllowed: false }));
    mount(); // FEED → probes feed[0] === "p1"
    await waitFor(() => expect(getEconomicsMock).toHaveBeenCalledWith("p1"));
  });

  it("GATED branch: renders the future-tense gated publishing + payout copy when the gate is closed", async () => {
    getEconomicsMock.mockResolvedValue(
      economics({ publicPublishingAllowed: false, disbursementAllowed: false }),
    );
    mount();
    // Both gated sentences render; neither "open" sentence appears.
    expect(await screen.findByText(GATE_PHRASES.publicSharing.whenGated)).toBeTruthy();
    expect(screen.getByText(GATE_PHRASES.disbursement.whenGated)).toBeTruthy();
    expect(screen.queryByText(PUBLIC_LANE_LABELS.publishingOpen)).toBeNull();
    expect(screen.queryByText(PUBLIC_LANE_LABELS.payoutsOpen)).toBeNull();
  });

  it("OPEN branch: renders the honest 'now open' state copy when the gate has cleared", async () => {
    getEconomicsMock.mockResolvedValue(
      economics({ publicPublishingAllowed: true, disbursementAllowed: true }),
    );
    mount();
    // Both "open" state sentences render once the live read resolves; the gated
    // sentences are gone.
    expect(await screen.findByText(PUBLIC_LANE_LABELS.publishingOpen)).toBeTruthy();
    expect(screen.getByText(PUBLIC_LANE_LABELS.payoutsOpen)).toBeTruthy();
    expect(screen.queryByText(GATE_PHRASES.publicSharing.whenGated)).toBeNull();
    expect(screen.queryByText(GATE_PHRASES.disbursement.whenGated)).toBeNull();
  });

  it("treats a getEconomics failure as gated (deny-by-default, no crash)", async () => {
    getEconomicsMock.mockRejectedValue(new Error("no provider"));
    mount();
    // The lane renders fine and shows the gated copy; nothing claims "open".
    expect(await screen.findByText(GATE_PHRASES.publicSharing.whenGated)).toBeTruthy();
    expect(screen.queryByText(PUBLIC_LANE_LABELS.publishingOpen)).toBeNull();
  });

  it("does not probe getEconomics on an empty feed (nothing to read → gated)", () => {
    mount({ feed: [] });
    expect(getEconomicsMock).not.toHaveBeenCalled();
    // Empty feed still renders the gated explainer copy (deny-by-default).
    expect(screen.getByText(GATE_PHRASES.publicSharing.whenGated)).toBeTruthy();
  });
});

describe("PublicLane — dark mode parity (M6)", () => {
  it("keeps dark: variants on its surfaces", () => {
    const { container } = mount();
    expect(container.querySelectorAll("[class*='dark:']").length).toBeGreaterThan(0);
  });
});
