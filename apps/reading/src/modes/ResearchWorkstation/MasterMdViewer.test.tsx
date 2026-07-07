/**
 * MasterMdViewer.test.tsx — the named-source synthesis read (SPR-04 M1).
 *
 * Pins the gates:
 *   - claim support renders as a NAMED source ("from <Title>, p.12")
 *     resolved through the provenance chain — never "[N chunks]" or a raw
 *     chunk id;
 *   - many chunks of ONE document collapse to ONE named source (the
 *     chunk→source translation, not "[3 chunks]");
 *   - a RESTRICTED source (servable=false) is NOT opened: it shows the
 *     honest "not available to open" state and never the body (§9.0);
 *   - a claim whose chunks all fail to resolve shows an honest
 *     "source unavailable", never a fabricated title (rigor #1).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import type { ChunkResponse, InvestigationSummary } from "../../lib/api";
import type { ParsedSynthesis } from "../../lib/synthesisParser";

const {
  getChunkMock,
  apiFetchMock,
  getTrajectoryMock,
  listStaleRefreshResolutionsMock,
  postTypedEventMock,
  processStaleRefreshPromotionMock,
  startInvestigationMock,
  recordSpawnRelationshipMock,
} = vi.hoisted(() => ({
  getChunkMock: vi.fn(),
  apiFetchMock: vi.fn(),
  getTrajectoryMock: vi.fn(),
  listStaleRefreshResolutionsMock: vi.fn(),
  postTypedEventMock: vi.fn(),
  processStaleRefreshPromotionMock: vi.fn(),
  startInvestigationMock: vi.fn(),
  recordSpawnRelationshipMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    getChunk: getChunkMock,
    apiFetch: apiFetchMock,
    getTrajectory: getTrajectoryMock,
    listStaleRefreshResolutions: listStaleRefreshResolutionsMock,
    postTypedEvent: postTypedEventMock,
    processStaleRefreshPromotion: processStaleRefreshPromotionMock,
    startInvestigation: startInvestigationMock,
  };
});
vi.mock("../../hooks/useInvestigationTree", () => ({
  recordSpawnRelationship: recordSpawnRelationshipMock,
}));
// Workspace actions + toast are side-effectful; stub them so the render is
// pure. We assert on what the reader SEES, not on panel side effects.
vi.mock("../../workspace/actions", () => ({
  openNotebook: vi.fn(),
  openPdfPanel: vi.fn(),
}));
vi.mock("../../components/lemon/LemonToast", () => ({
  toast: { ok: vi.fn(), err: vi.fn() },
}));

import MasterMdViewer, {
  ClaimBlock,
  STALE_REUSE_REFRESH_STORAGE_KEY,
  reviewDueDecorationsFor,
} from "./MasterMdViewer";
import { REVIEW_DUE_CLASS } from "../../reading-physics/augmentations/review-due";
import { anchorKey } from "../../reading-physics/facets/decorations";
import type { ClaimId } from "../../reading-physics/types";
import type { ParsedClaim } from "../../lib/synthesisParser";

// jsdom does not implement ResizeObserver, but MasterMdViewer's geometry pass
// (Living-Roadmap SPR-02 round 2) constructs one on mount. Install a minimal
// no-op global stub so every render works; the recompute-trigger test below
// replaces it with a capturing stub for the one assertion that drives the
// callback, and restores this afterward.
const PRIOR_RESIZE_OBSERVER = (globalThis as { ResizeObserver?: unknown })
  .ResizeObserver;
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
beforeEach(() => {
  const storage = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
      removeItem: (key: string) => storage.delete(key),
      clear: () => storage.clear(),
    },
  });
  (globalThis as { ResizeObserver?: unknown }).ResizeObserver =
    NoopResizeObserver as unknown as typeof ResizeObserver;
  listStaleRefreshResolutionsMock.mockResolvedValue({ count: 0, resolutions: [] });
});

afterEach(() => {
  cleanup();
  window.localStorage.removeItem(STALE_REUSE_REFRESH_STORAGE_KEY);
  getChunkMock.mockReset();
  getTrajectoryMock.mockReset();
  listStaleRefreshResolutionsMock.mockReset();
  postTypedEventMock.mockReset();
  processStaleRefreshPromotionMock.mockReset();
  startInvestigationMock.mockReset();
  recordSpawnRelationshipMock.mockReset();
  if (PRIOR_RESIZE_OBSERVER === undefined) {
    delete (globalThis as { ResizeObserver?: unknown }).ResizeObserver;
  } else {
    (globalThis as { ResizeObserver?: unknown }).ResizeObserver =
      PRIOR_RESIZE_OBSERVER;
  }
});

function chunk(over: Partial<ChunkResponse>): ChunkResponse {
  return {
    chunk_id: "c",
    text: "body",
    section_path: "p.12",
    token_count: 10,
    document_id: "doc-1",
    document_title: "On Growth and Form",
    source_tier: 2,
    servable: true,
    servability: null,
    ...over,
  };
}

function investigationSummary(
  over: Partial<InvestigationSummary> & { investigation_id: string },
): InvestigationSummary {
  return {
    question: "Refresh prior insight",
    status: "completed",
    started_at: null,
    completed_at: null,
    cost_usd_total: 0,
    parent_investigation_id: null,
    spawn_context: null,
    ...over,
  };
}

function synth(over: Partial<ParsedSynthesis> = {}): ParsedSynthesis {
  return {
    investigationId: "inv-parent",
    synthesisId: null,
    thesisSummary: "A thesis.",
    components: [
      {
        index: 1,
        claim: "The claim holds.",
        confidence: "high",
        effectiveSourceTier: 2,
        hedgingRequired: false,
        chunkIds: ["c1"],
        supportingPathIndices: [],
      },
    ],
    falsificationConditions: [],
    executionRisks: [],
    recommendation: "proceed",
    hardConstraintsSatisfied: true,
    totalCostUsd: 0.01,
    question: "Why?",
    masterMdPath: null,
    domainsPatched: [],
    chunkCitations: { c1: [1] },
    qualityScore: null,
    reuseProvenance: [],
    compoundingStat: null,
    staleResolutionsByEntityId: {},
    ...over,
  };
}

describe("MasterMdViewer — no static save-to-notebook in the research flow (SPR-06 M2)", () => {
  it("renders no 'Save to notebook' affordance (the auto-notebook supersedes it)", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(<MasterMdViewer synthesis={synth()} />);
    // Wait for the synthesis to render so any header affordance would be present.
    await waitFor(() => expect(screen.getByText("The claim holds.")).toBeTruthy());
    // The static save-to-notebook button is GONE — the operator's directive is
    // "automatically generated, not statically"; the auto-notebook is the surface.
    expect(screen.queryByText(/save to notebook/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /save to notebook/i })).toBeNull();
  });
});

describe("MasterMdViewer — named-source read (M1)", () => {
  it("renders the source as a named title + locator, never [N chunks]", async () => {
    getChunkMock.mockResolvedValue(
      chunk({ chunk_id: "c1", document_title: "On Growth and Form", section_path: "p.12" }),
    );
    render(<MasterMdViewer synthesis={synth()} />);
    await waitFor(() =>
      expect(screen.getByText(/On Growth and Form/)).toBeTruthy(),
    );
    expect(screen.getByText(/from On Growth and Form/)).toBeTruthy();
    expect(screen.getByText(/p\.12/)).toBeTruthy();
    // The jargon must be gone.
    expect(screen.queryByText(/\[.*chunk.*\]/i)).toBeNull();
    expect(screen.queryByText("c1")).toBeNull();
  });

  it("collapses many chunks of one document into one named source", async () => {
    getChunkMock.mockImplementation(async (id: string) =>
      chunk({ chunk_id: id, document_id: "doc-1", document_title: "One Paper" }),
    );
    render(
      <MasterMdViewer
        synthesis={synth({
          components: [
            {
              index: 1,
              claim: "Backed by three chunks of one paper.",
              confidence: "high",
              effectiveSourceTier: 2,
              hedgingRequired: false,
              chunkIds: ["c1", "c2", "c3"],
              supportingPathIndices: [],
            },
          ],
          chunkCitations: { c1: [1], c2: [1], c3: [1] },
        })}
      />,
    );
    await waitFor(() =>
      expect(screen.getAllByText(/from One Paper/).length).toBe(1),
    );
  });

  it("does NOT open a restricted source — shows 'not available to open'", async () => {
    getChunkMock.mockResolvedValue(
      chunk({
        chunk_id: "c1",
        document_title: "A Restricted Book",
        text: "", // body withheld by the endpoint
        servable: false,
        servability: "restricted",
      }),
    );
    render(<MasterMdViewer synthesis={synth()} />);
    await waitFor(() =>
      expect(screen.getByText(/A Restricted Book/)).toBeTruthy(),
    );
    expect(screen.getByText(/not available to open/)).toBeTruthy();
    // It is NOT a button (can't be clicked to open). The named source is a
    // plain span in the not-servable branch.
    expect(screen.queryByTitle(/Click to preview/)).toBeNull();
  });

  it("shows 'source unavailable' when no chunk resolves, never a fake title", async () => {
    getChunkMock.mockRejectedValue(new Error("404"));
    render(<MasterMdViewer synthesis={synth()} />);
    await waitFor(() =>
      expect(screen.getByText(/source unavailable/)).toBeTruthy(),
    );
  });

  // ── SPR-10 M1 — the IP-holder dimension ("whose work grounds this") ──

  it("shows 'published by X' when the source has a resolved IP holder", async () => {
    getChunkMock.mockResolvedValue(
      chunk({ chunk_id: "c1", document_title: "On Growth and Form", ip_holder_name: "MIT Press" }),
    );
    render(<MasterMdViewer synthesis={synth()} />);
    await waitFor(() => expect(screen.getByText(/On Growth and Form/)).toBeTruthy());
    expect(screen.getByText(/published by MIT Press/)).toBeTruthy();
  });

  it("invents no owner when ip_holder_name is null (honest unknown)", async () => {
    getChunkMock.mockResolvedValue(
      chunk({ chunk_id: "c1", document_title: "On Growth and Form", ip_holder_name: null }),
    );
    render(<MasterMdViewer synthesis={synth()} />);
    await waitFor(() => expect(screen.getByText(/On Growth and Form/)).toBeTruthy());
    // No fabricated "published by …" when the owner is unknown.
    expect(screen.queryByText(/published by/)).toBeNull();
  });

  it("does NOT expose the owner of a restricted source (§9.0 protected attribution)", async () => {
    // The endpoint withholds ip_holder_name for a non-servable source; the
    // surface must not show "published by …" on the restricted branch.
    getChunkMock.mockResolvedValue(
      chunk({
        chunk_id: "c1",
        document_title: "A Restricted Book",
        text: "",
        servable: false,
        servability: "restricted",
        ip_holder_name: null,
      }),
    );
    render(<MasterMdViewer synthesis={synth()} />);
    await waitFor(() => expect(screen.getByText(/A Restricted Book/)).toBeTruthy());
    expect(screen.getByText(/not available to open/)).toBeTruthy();
    expect(screen.queryByText(/published by/)).toBeNull();
  });
});

// ── SPR-11 M3 — the inline-rubric quality cue (present / low / absent) ──

describe("MasterMdViewer — quality cue (SPR-11 M3)", () => {
  it("renders nothing when no score was persisted (absent → no fabricated cue)", () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(<MasterMdViewer synthesis={synth({ qualityScore: null })} />);
    // No quality wording at all — the absent case is honest by saying nothing.
    expect(screen.queryByText(/quality bar/i)).toBeNull();
    expect(screen.queryByText(/another pass/i)).toBeNull();
  });

  it("shows a quiet positive cue when the score clears the bar", () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(
      <MasterMdViewer
        synthesis={synth({
          qualityScore: {
            composite: 0.82,
            voiceStyle: 0.8,
            conviction: 0.75,
            citationDensity: 1.0,
            constraintCompliance: 1.0,
            notes: "voice=0.80 conviction=0.75 citation_density=1.00 constraint=1.00",
          },
        })}
      />,
    );
    expect(screen.getByText(/clears our quality bar/i)).toBeTruthy();
    // A passing answer is NOT flagged for a re-run.
    expect(screen.queryByText(/another pass/i)).toBeNull();
  });

  it("visibly flags a LOW score so the operator knows to re-run / edit", () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(
      <MasterMdViewer
        synthesis={synth({
          qualityScore: {
            composite: 0.22,
            voiceStyle: 0.3,
            conviction: 0.2,
            citationDensity: 0.0,
            constraintCompliance: 0.0,
            notes: "voice=0.30 conviction=0.20 citation_density=0.00 constraint=0.00",
          },
        })}
      />,
    );
    expect(screen.getByText(/another pass/i)).toBeTruthy();
    expect(screen.getByText(/under our quality bar/i)).toBeTruthy();
    // It must NOT also claim the answer cleared the bar.
    expect(screen.queryByText(/clears our quality bar/i)).toBeNull();
  });

  it("offers the sub-score breakdown behind a collapsed toggle (quiet by default)", () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(
      <MasterMdViewer
        synthesis={synth({
          qualityScore: {
            composite: 0.82,
            voiceStyle: 0.8,
            conviction: 0.75,
            citationDensity: 1.0,
            constraintCompliance: 1.0,
            notes: "voice=0.80 conviction=0.75 citation_density=1.00 constraint=1.00",
          },
        })}
      />,
    );
    // The breakdown exists but is not the default surface — it's behind a
    // <summary> toggle. The labels are plain words, not scorer field names.
    expect(screen.getByText(/the detail/i)).toBeTruthy();
    expect(screen.getByText(/Voice and style/)).toBeTruthy();
    expect(screen.getByText(/Sourcing/)).toBeTruthy();
  });

  it("hides the breakdown when the note carried no sub-scores (no empty rows)", () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(
      <MasterMdViewer
        synthesis={synth({
          qualityScore: {
            composite: 0.1,
            voiceStyle: null,
            conviction: null,
            citationDensity: null,
            constraintCompliance: null,
            notes: "synthesizer declined to produce a thesis (insufficient_evidence)",
          },
        })}
      />,
    );
    // Low score still flags for a re-run …
    expect(screen.getByText(/another pass/i)).toBeTruthy();
    // … but with no sub-scores there is no "the detail" toggle.
    expect(screen.queryByText(/the detail/i)).toBeNull();
  });
});

// ── SPR-02 — BYTE-EQUIVALENCE of the re-homed §9.0 render ───────────────────
//
// The §9.0 servability / IP-holder annotations were re-homed out of the inline
// SourceCitation branch into a ServabilityAugmentation that DECLARES decorations
// into the new `decorations` facet; the surface ENACTS them. The slice's whole
// claim is that the rendered DOM is BYTE-IDENTICAL to the pre-slice render. The
// baseline strings below are the recorded pre-SPR-02 SourceCitation output
// (MasterMdViewer.tsx). Any diff is a regression (rigor #1) — do not "adjust"
// the baseline. Both a SERVABLE and a NON-servable source are exercised in one
// render (rigor #3).

const SERVABLE_BUTTON_CLASS =
  "text-[11px] text-ink-soft dark:text-starlight bg-ice-3 dark:bg-charcoal-1 hover:bg-ice-4 px-1.5 py-0.5 rounded transition-colors";
const RESTRICTED_SPAN_CLASS =
  "text-[11px] text-ink-soft dark:text-starlight bg-ice-2 dark:bg-charcoal-1 px-1.5 py-0.5 rounded inline-flex items-center gap-1";

/** A synthesis with two claims: one cites a SERVABLE source, the other a
 *  NON-servable source — so a single render exercises both §9.0 branches. */
function twoSourceSynth(): ParsedSynthesis {
  return synth({
    components: [
      {
        index: 1,
        claim: "Backed by an open source.",
        confidence: "high",
        effectiveSourceTier: 2,
        hedgingRequired: false,
        chunkIds: ["open-1"],
        supportingPathIndices: [],
      },
      {
        index: 2,
        claim: "Backed by a restricted source.",
        confidence: "moderate",
        effectiveSourceTier: 3,
        hedgingRequired: false,
        chunkIds: ["gated-1"],
        supportingPathIndices: [],
      },
    ],
    chunkCitations: { "open-1": [1], "gated-1": [2] },
  });
}

describe("MasterMdViewer — byte-equivalence of the re-homed §9.0 render (SPR-02)", () => {
  it("emits the EXACT servable button + restricted span the inline code produced", async () => {
    getChunkMock.mockImplementation(async (id: string) => {
      if (id === "open-1") {
        return chunk({
          chunk_id: "open-1",
          document_id: "doc-open",
          document_title: "An Open Paper",
          section_path: "p.7",
          servable: true,
          servability: null,
          ip_holder_name: "MIT Press",
        });
      }
      return chunk({
        chunk_id: "gated-1",
        document_id: "doc-gated",
        document_title: "A Restricted Book",
        section_path: "p.99",
        text: "", // body withheld by the endpoint
        servable: false,
        servability: "restricted",
        ip_holder_name: null, // §9.0 withholds the owner with the body
      });
    });

    const { container } = render(<MasterMdViewer synthesis={twoSourceSynth()} />);

    // ── Servable source: a BUTTON, exact class string + tooltip + content ──
    const openBtn = await waitFor(() =>
      screen.getByTitle("Click to preview · ⌘-click to open the source"),
    );
    expect(openBtn.tagName).toBe("BUTTON");
    expect(openBtn.getAttribute("class")).toBe(SERVABLE_BUTTON_CLASS);
    expect(openBtn.textContent).toBe("from An Open Paper, p.7, published by MIT Press");

    // ── Restricted source: a SPAN, exact class string + tooltip + the
    //     "not available to open" inner span; NO body, NO owner ──
    const gatedSpan = screen.getByTitle(
      "This source isn’t available to open here (its license restricts it).",
    );
    expect(gatedSpan.tagName).toBe("SPAN");
    expect(gatedSpan.getAttribute("class")).toBe(RESTRICTED_SPAN_CLASS);
    expect(gatedSpan.textContent).toBe(
      "from A Restricted Book, p.99· not available to open",
    );
    // The inner "· not available to open" span carries its exact class.
    const inner = gatedSpan.querySelector("span");
    expect(inner?.getAttribute("class")).toBe(
      "text-[10px] text-shadow-1 dark:text-moonlight",
    );

    // §9.0: the withheld body never appears; the restricted source exposes
    // NO owner; and exactly ONE openable button exists (the servable source).
    expect(container.textContent).not.toContain("body");
    expect(gatedSpan.textContent).not.toContain("published by");
    expect(
      container.querySelectorAll("button[title^='Click to preview']").length,
    ).toBe(1);
  });

  it("§9.0: a non-servable source keeps WITHHOLDING — no decoration reveals it", async () => {
    getChunkMock.mockResolvedValue(
      chunk({
        chunk_id: "c1",
        document_title: "A Restricted Book",
        text: "", // body withheld
        servable: false,
        servability: "restricted",
        ip_holder_name: null,
      }),
    );
    const { container } = render(<MasterMdViewer synthesis={synth()} />);
    await waitFor(() => expect(screen.getByText(/A Restricted Book/)).toBeTruthy());
    // The verdict decoration declared RESTRICTED, so the surface enacts the
    // withholding span — never an openable button.
    expect(screen.queryByTitle(/Click to preview/)).toBeNull();
    expect(screen.getByText(/not available to open/)).toBeTruthy();
    expect(container.querySelector("button[title^='Click to preview']")).toBeNull();
  });
});

// ── SPR-08 M5 — review-due LIVENESS (toggle-ON path) + default-off pin ───────
//
// The capstone's PR-7 claim is that review-due is GENUINELY live when flipped:
// a populated `dueClaims` lights up the right claim span through the real
// augmentation→facet→map→span chain, not a stub. The module toggle
// (`REVIEW_DUE_ENABLED`) stays default-OFF and the surface still hands an empty
// due set, so we drive the toggle-ON path through the exported PURE seam
// (`reviewDueDecorationsFor`, which does not read the toggle), then enact the
// resolved decoration through the exported `ClaimBlock` — the same enact the
// mount uses. Real review-state resolution from the substrate is still deferred
// (spr-08-review-state-resolution-gap.md); this drives the seam with a populated
// set to prove the wiring is live, not the resolver.

function reviewDueSynth(): ParsedSynthesis {
  return synth({
    components: [
      {
        index: 1,
        claim: "A claim that is due for review.",
        confidence: "high",
        effectiveSourceTier: 2,
        hedgingRequired: false,
        chunkIds: ["c1"],
        supportingPathIndices: [],
      },
      {
        index: 2,
        claim: "A claim that is NOT due for review.",
        confidence: "moderate",
        effectiveSourceTier: 3,
        hedgingRequired: false,
        chunkIds: ["c2"],
        supportingPathIndices: [],
      },
    ],
    chunkCitations: { c1: [1], c2: [2] },
  });
}

const noopPreview = (_chunkId: string) => {};

describe("MasterMdViewer — review-due liveness (SPR-08 M5)", () => {
  it("populated dueClaims → the resolved decoration for the due claim carries the class + title", () => {
    const resolved = reviewDueDecorationsFor(reviewDueSynth(), [
      { claimId: "1", dueLabel: "Due today" },
    ]);
    // The augmentation→facet→map chain produced a decoration keyed to claim 1
    // (the right claim), carrying the closed-vocabulary class + substrate cue.
    const due = resolved.get(
      anchorKey({ kind: "claim", claimId: "1" as ClaimId }),
    );
    expect(due).toBeDefined();
    expect(due!.classNames).toContain(REVIEW_DUE_CLASS);
    expect(due!.title).toBe("Due today");
    // Claim 2 was not in the due set — no decoration, never fabricated.
    expect(
      resolved.get(anchorKey({ kind: "claim", claimId: "2" as ClaimId })),
    ).toBeUndefined();
  });

  it("enacts the class + title onto the DUE claim span, and onto NO other claim span", () => {
    // ClaimBlock mounts NamedSources, which resolves cited chunks async; mock
    // the fetch so a late-settling promise can't crash after the test ends.
    getChunkMock.mockImplementation(async (id: string) => chunk({ chunk_id: id }));
    const syn = reviewDueSynth();
    const resolved = reviewDueDecorationsFor(syn, [
      { claimId: "1", dueLabel: "Due today" },
    ]);
    const dueClaim = syn.components[0] as ParsedClaim;
    const notDueClaim = syn.components[1] as ParsedClaim;

    const { container } = render(
      <>
        <ClaimBlock
          claim={dueClaim}
          onChunkClick={noopPreview}
          reviewDue={resolved.get(
            anchorKey({ kind: "claim", claimId: "1" as ClaimId }),
          )}
        />
        <ClaimBlock
          claim={notDueClaim}
          onChunkClick={noopPreview}
          reviewDue={resolved.get(
            anchorKey({ kind: "claim", claimId: "2" as ClaimId }),
          )}
        />
      </>,
    );

    // The DUE claim span carries the review-due class + the substrate cue title.
    const dueSpan = container.querySelector('[data-claim-id="1"]');
    expect(dueSpan).not.toBeNull();
    expect(dueSpan!.getAttribute("class")).toContain(REVIEW_DUE_CLASS);
    expect(dueSpan!.getAttribute("title")).toBe("Due today");

    // The NOT-due claim span gets NEITHER (the class lands only where due).
    const notDueSpan = container.querySelector('[data-claim-id="2"]');
    expect(notDueSpan).not.toBeNull();
    expect(notDueSpan!.getAttribute("class") ?? "").not.toContain(REVIEW_DUE_CLASS);
    expect(notDueSpan!.getAttribute("title")).toBeNull();
  });
});

// ── SPR-08 M5 — DEFAULT-OFF byte-equivalence of the claim span ───────────────
//
// A DIRECT, named assertion that with the default (`REVIEW_DUE_ENABLED = false`)
// no claim span carries the `review-due` class or a review-due title — i.e. the
// review-due augmentation is byte-equivalent to absent on the shipped default.
// (The SPR-02 byte-equivalence test proves the whole render is exact
// transitively; this pins the review-due-specific default-off claim directly so
// the deferral doc's wording is literally true.)

// ── Living-Roadmap SPR-02 — the geometry pass is MOUNTED in the surface (M1/M2) ─
//
// Proves the surface threads a LIVE layout-map through its render contexts (M1)
// and mounts the minimap as a SECOND pass (M2). jsdom does no layout, so the
// measured rects are 0×0 and (correctly) dropped — so this asserts the WIRING is
// present (the minimap container renders, the existing widget render is preserved
// against the live map) rather than re-proving the resolver, which the headless
// readingGeometryPass.test.ts pins against a populated DOM. Separating "the surface
// mounts the live map" (here) from "the layout-map function returns a rect this
// facet consumes" (there) is the honesty rigor #1 asks for.

describe("MasterMdViewer — geometry pass mounted in the surface (Living-Roadmap SPR-02)", () => {
  it("mounts the minimap as a second pass (the wiring is present)", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    const { container } = render(<MasterMdViewer synthesis={synth()} />);
    await waitFor(() => expect(screen.getByText(/On Growth and Form/)).toBeTruthy());
    // The minimap's second pass renders its container (wiring proof). Review-due
    // is default-off ⇒ no marks ⇒ the container is the honest empty/aria-hidden
    // fingerprint, but it IS mounted (proving the live map flows to a second pass).
    expect(container.querySelector(".reading-minimap")).not.toBeNull();
  });

  it("the header quality cue still renders against the live map (geometry-independent, preserved)", () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(
      <MasterMdViewer
        synthesis={synth({
          qualityScore: {
            composite: 0.82,
            voiceStyle: 0.8,
            conviction: 0.75,
            citationDensity: 1.0,
            constraintCompliance: 1.0,
            notes: "voice=0.80 conviction=0.75 citation_density=1.00 constraint=1.00",
          },
        })}
      />,
    );
    // QualityCue is geometry-independent: threading the live map (vs the old
    // EMPTY_LAYOUT_MAP) leaves its render byte-equivalent — it still clears the bar.
    expect(screen.getByText(/clears our quality bar/i)).toBeTruthy();
  });
});

// ── Living-Roadmap SPR-02 round 2 — the REAL recompute trigger is exercised ──
//
// Round 1 mounted a `window` scroll listener that NEVER fires on this surface
// (MasterMdViewer scrolls inside an inner `overflow-y-auto` ancestor, and the base
// geometry is root-relative ⇒ scroll-invariant anyway). Round 2 replaced it with a
// ResizeObserver on the ARTICLE, the true recompute trigger (layout-size / reflow
// changes). This test drives that trigger end-to-end rather than asserting a
// function in isolation: it stubs ResizeObserver to CAPTURE the callback + the
// observed node, proves the observer is bound to the article element, then fires
// the callback and (after the debounce) asserts a fresh measurement pass ran — the
// mounted map is recomputed from the just-changed DOM, not from a dead listener.

interface CapturedRO {
  callback: ResizeObserverCallback;
  observed: Element[];
  disconnected: boolean;
}

describe("MasterMdViewer — ResizeObserver recompute trigger (Living-Roadmap SPR-02 round 2)", () => {
  it("recomputes the layout-map when the captured ResizeObserver callback fires", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));

    // ── Stub ResizeObserver (jsdom has none) so we can capture its callback and
    //    drive it deterministically. We record the observed nodes + disconnect. ──
    const observers: CapturedRO[] = [];
    const RealResizeObserver = (globalThis as { ResizeObserver?: unknown })
      .ResizeObserver;
    class StubResizeObserver {
      private readonly rec: CapturedRO;
      constructor(callback: ResizeObserverCallback) {
        this.rec = { callback, observed: [], disconnected: false };
        observers.push(this.rec);
      }
      observe(el: Element) {
        this.rec.observed.push(el);
      }
      unobserve() {}
      disconnect() {
        this.rec.disconnected = true;
      }
    }
    (globalThis as { ResizeObserver?: unknown }).ResizeObserver =
      StubResizeObserver as unknown as typeof ResizeObserver;

    // ── Spy getBoundingClientRect: give the article a real rect so the measure
    //    pass walks a populated root, and COUNT the reads on the article so we can
    //    detect a second measurement pass after the trigger fires. jsdom returns
    //    all-zeros otherwise. ──
    let articleRectReads = 0;
    const geomSpy = vi
      .spyOn(HTMLElement.prototype, "getBoundingClientRect")
      .mockImplementation(function (this: HTMLElement) {
        if (this.tagName === "ARTICLE") articleRectReads += 1;
        const claimId = this.getAttribute("data-claim-id");
        // The claim span carries a real rect (so a measurement resolves it); the
        // article is the origin; everything else is unlaid (0×0, dropped).
        const r = claimId
          ? { top: 120, left: 20, width: 600, height: 40 }
          : this.tagName === "ARTICLE"
            ? { top: 0, left: 0, width: 800, height: 4000 }
            : { top: 0, left: 0, width: 0, height: 0 };
        return {
          top: r.top,
          left: r.left,
          width: r.width,
          height: r.height,
          right: r.left + r.width,
          bottom: r.top + r.height,
          x: r.left,
          y: r.top,
          toJSON() {
            return r;
          },
        } as DOMRect;
      });

    vi.useFakeTimers();
    try {
      render(<MasterMdViewer synthesis={synth()} />);

      // The trigger is wired to the ARTICLE element (NOT window): exactly one
      // observer was constructed and it observes the article that carries the
      // measured claim spans.
      expect(observers).toHaveLength(1);
      const ro = observers[0];
      expect(ro.observed).toHaveLength(1);
      expect((ro.observed[0] as HTMLElement).tagName).toBe("ARTICLE");

      // The initial synchronous useLayoutEffect measure already read the article.
      const readsAfterInitialMeasure = articleRectReads;
      expect(readsAfterInitialMeasure).toBeGreaterThan(0);

      // Fire the REAL recompute trigger (a layout-size change) and let the debounce
      // settle. Only after the trailing-edge timer should the recompute run.
      act(() => {
        ro.callback([], ro as unknown as ResizeObserver);
      });
      // Before the debounce elapses, no extra measurement pass has run.
      expect(articleRectReads).toBe(readsAfterInitialMeasure);
      act(() => {
        vi.advanceTimersByTime(150); // > GEOMETRY_RECOMPUTE_DEBOUNCE_MS (100)
      });
      // The captured callback drove a FRESH measurement pass: the article was
      // re-measured (recompute ran through the real trigger, not a dead listener).
      expect(articleRectReads).toBeGreaterThan(readsAfterInitialMeasure);
    } finally {
      vi.useRealTimers();
      geomSpy.mockRestore();
      if (RealResizeObserver === undefined) {
        delete (globalThis as { ResizeObserver?: unknown }).ResizeObserver;
      } else {
        (globalThis as { ResizeObserver?: unknown }).ResizeObserver =
          RealResizeObserver;
      }
    }
  });
});

// ── SPR-10 M3/M4/M6 — the reuse-provenance footnote (present / empty / link) ──
//
// Present-only (the qualityScore === null discipline): with reuseProvenance
// empty AND no compounding stat, the affordance node is ABSENT from the DOM (a
// queryBy… returns null) — so the no-reuse render is byte-identical to today and
// the SPR-02 byte-equivalence test above is unaffected. With data present, each
// reused insight links to its prior investigation's EXISTING /inv/:id route (M6),
// and the stat line renders only the numbers it actually has (M4).

describe("MasterMdViewer — reuse provenance footnote (SPR-10 M3/M4/M6)", () => {
  it("renders NOTHING when the run reused nothing (empty + no stat → no affordance node)", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(
      <MasterMdViewer
        synthesis={synth({ reuseProvenance: [], compoundingStat: null })}
      />,
    );
    await waitFor(() => expect(screen.getByText("The claim holds.")).toBeTruthy());
    // Present-only: the whole affordance is absent — no node, no heading, no
    // stat line. This is the byte-identical no-reuse render.
    expect(screen.queryByTestId("reuse-provenance")).toBeNull();
    expect(screen.queryByText(/Reuse provenance/i)).toBeNull();
    expect(screen.queryByText(/reused .* insight/i)).toBeNull();
  });

  it("renders one link per reused insight, each to the prior investigation's /inv/ route (M3/M6)", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(
      <MasterMdViewer
        synthesis={synth({
          reuseProvenance: [
            { unitId: "unit-aaa", sourceInvestigationId: "inv-src-1", score: 0.91 },
            { unitId: "unit-bbb", sourceInvestigationId: "inv-src-2", score: 0.83 },
          ],
          // reuse present, no per-run measurement (the common case) → no stat line.
          compoundingStat: null,
        })}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("reuse-provenance")).toBeTruthy());

    // Non-vacuity: the EXACT unit ids appear as link text, and each link's href
    // resolves to the EXISTING /inv/:id route (no orphan; SPR-01 reachability).
    const linkA = screen.getByText("prior insight unit-aaa");
    const linkB = screen.getByText("prior insight unit-bbb");
    expect(linkA.getAttribute("href")).toBe("/inv/inv-src-1");
    expect(linkB.getAttribute("href")).toBe("/inv/inv-src-2");
    for (const href of [
      linkA.getAttribute("href"),
      linkB.getAttribute("href"),
    ]) {
      expect(href).toMatch(/^\/inv\//);
    }
  });

  it("renders a known-source insight WITHOUT a source as plain text (honest, no dead link)", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(
      <MasterMdViewer
        synthesis={synth({
          reuseProvenance: [
            { unitId: "unit-orphan", sourceInvestigationId: null, score: null },
          ],
          compoundingStat: null,
        })}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("reuse-provenance")).toBeTruthy());
    const node = screen.getByText("prior insight unit-orphan");
    // No source ⇒ plain span, NOT an <a> (never a dead link to a missing route).
    expect(node.tagName).not.toBe("A");
    expect(node.getAttribute("href")).toBeNull();
  });

  it("renders the reuse LIST but NO stat line when there's reuse and no measurement (M4 gating)", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(
      <MasterMdViewer
        synthesis={synth({
          reuseProvenance: [
            { unitId: "u1", sourceInvestigationId: "inv-a", score: 0.9 },
            { unitId: "u2", sourceInvestigationId: "inv-b", score: 0.8 },
          ],
          // No per-run measurement event → no stat (M4: "null when no measurement").
          compoundingStat: null,
        })}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("reuse-provenance")).toBeTruthy());
    // The reuse list (M3) renders — the reused count is surfaced HERE …
    expect(screen.getByText("prior insight u1")).toBeTruthy();
    expect(screen.getByText("prior insight u2")).toBeTruthy();
    // … but there is NO "reused N" stat line: a stat without a measurement would
    // imply one happened (M4 honesty). The count is the list, never a fabricated stat.
    // (`\d+` targets the stat "reused 2 insights", not the list heading
    // "Reused prior insights" — which is M3's list, and SHOULD render.)
    expect(screen.queryByText(/reused \d+ insight/i)).toBeNull();
    expect(screen.queryByText(/re-derivation/)).toBeNull();
    expect(screen.queryByText(/fewer source/)).toBeNull();
  });

  it("marks stale-advisory reused insights with a refresh cue", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(
      <MasterMdViewer
        synthesis={synth({
          reuseProvenance: [
            { unitId: "unit-current", sourceInvestigationId: "inv-current", score: 0.92 },
            {
              unitId: "unit-stale",
              sourceInvestigationId: "inv-stale",
              score: 0.81,
              staleRefreshAdvisory: true,
            },
          ],
          compoundingStat: null,
        })}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("reuse-provenance")).toBeTruthy());

    expect(screen.getByText("prior insight unit-current")).toBeTruthy();
    expect(screen.getByText("prior insight unit-stale")).toBeTruthy();
    expect(screen.getByText("refresh before current use")).toBeTruthy();
  });

  it("shows resolved stale advisory state from graph staleness resolution replay", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(
      <MasterMdViewer
        synthesis={synth({
          investigationId: "inv-parent",
          reuseProvenance: [
            {
              unitId: "unit-stale",
              sourceInvestigationId: "inv-source",
              score: 0.81,
              staleRefreshAdvisory: true,
              staleAdvisoryEdgeIds: ["edge-stale-personnel"],
              staleAdvisoryResolutions: [
                {
                  flagId: "stale-edge-stale-personnel-personnel",
                  entityKind: "edge",
                  entityId: "edge-stale-personnel",
                  status: "refreshed",
                  notes: "resolved by stale refresh promotion",
                },
              ],
            },
          ],
          compoundingStat: null,
        })}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("reuse-provenance")).toBeTruthy());

    const cue = screen.getByText("stale advisory resolved");
    expect(cue.getAttribute("title")).toBe(
      "edge-stale-personnel: refreshed · resolved by stale refresh promotion",
    );
    expect(screen.queryByText("refresh before current use")).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Refresh prior insight unit-stale" }),
    ).toBeNull();
  });

  it("summarizes resolved and unresolved stale advisory edges in the reuse block", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(
      <MasterMdViewer
        synthesis={synth({
          investigationId: "inv-parent",
          reuseProvenance: [
            {
              unitId: "unit-partial",
              sourceInvestigationId: "inv-source",
              score: 0.81,
              staleRefreshAdvisory: true,
              staleAdvisoryEdgeIds: ["edge-resolved", "edge-unresolved"],
              staleAdvisoryResolutions: [
                {
                  flagId: "stale-edge-resolved-personnel",
                  entityKind: "edge",
                  entityId: "edge-resolved",
                  status: "refreshed",
                  notes: "resolved by stale refresh promotion",
                },
              ],
            },
          ],
          compoundingStat: null,
        })}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("reuse-provenance")).toBeTruthy());

    expect(screen.getByText("1 resolved stale edge · 1 unresolved")).toBeTruthy();
    expect(screen.getByText("refresh before current use")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Refresh prior insight unit-partial" }),
    ).toBeTruthy();
  });

  it("renders graph-wide stale resolutions from the API helper", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    listStaleRefreshResolutionsMock.mockResolvedValue({
      count: 1,
      resolutions: [
        {
          event_id: "evt-resolution",
          investigation_id: "inv-refresh",
          emitted_at: "2026-07-07T15:05:00Z",
          parent_event_id: "evt-candidate",
          flag_id: "stale-edge-one-personnel",
          entity_kind: "edge",
          entity_id: "edge-one",
          status: "confirmed_stale",
          notes: "resolved by stale refresh promotion",
        },
        {
          event_id: "evt-dismissed",
          investigation_id: "inv-refresh",
          emitted_at: "2026-07-07T15:04:00Z",
          parent_event_id: null,
          flag_id: "stale-edge-two-market",
          entity_kind: "edge",
          entity_id: "edge-two",
          status: "dismissed",
          notes: "",
        },
      ],
    });

    render(
      <MasterMdViewer
        synthesis={synth({
          reuseProvenance: [],
          compoundingStat: null,
        })}
      />,
    );

    expect(await screen.findByText("Graph stale resolutions")).toBeTruthy();
    expect(screen.getByText("1 confirmed stale · 1 dismissed")).toBeTruthy();
    expect(screen.getByText("edge-one: confirmed stale")).toBeTruthy();
    expect(screen.getByText("resolved by stale refresh promotion")).toBeTruthy();
    expect(listStaleRefreshResolutionsMock).toHaveBeenCalledWith({ limit: 25 });
  });

  it("launches a child refresh research from a stale-advisory reused insight", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    startInvestigationMock.mockResolvedValue({
      investigation_id: "inv-refresh-child",
      status: "in_progress",
      start_event_id: "evt-start",
    });
    render(
      <MasterMdViewer
        synthesis={synth({
          investigationId: "inv-parent",
          reuseProvenance: [
            {
              unitId: "unit-stale",
              sourceInvestigationId: "inv-source",
              score: 0.81,
              staleRefreshAdvisory: true,
            },
          ],
          compoundingStat: null,
        })}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("reuse-provenance")).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "Refresh prior insight unit-stale" }));

    await waitFor(() =>
      expect(startInvestigationMock).toHaveBeenCalledWith(
        expect.objectContaining({
          parent_investigation_id: "inv-parent",
          spawn_context:
            "stale-reuse-refresh unit_id=unit-stale source_investigation_id=inv-source",
        }),
      ),
    );
    expect(startInvestigationMock.mock.calls[0][0].question).toContain("unit-stale");
    expect(recordSpawnRelationshipMock).toHaveBeenCalledWith(
      "inv-refresh-child",
      "inv-parent",
    );
    const link = await screen.findByText("Open refresh research");
    expect(link.getAttribute("href")).toBe("/inv/inv-refresh-child");
  });

  it("keeps the refresh child link after remount without launching again", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    window.localStorage.setItem(
      STALE_REUSE_REFRESH_STORAGE_KEY,
      JSON.stringify({
        "inv-parent|unit-stale|inv-source": "inv-refresh-existing",
      }),
    );

    render(
      <MasterMdViewer
        synthesis={synth({
          investigationId: "inv-parent",
          reuseProvenance: [
            {
              unitId: "unit-stale",
              sourceInvestigationId: "inv-source",
              score: 0.81,
              staleRefreshAdvisory: true,
            },
          ],
          compoundingStat: null,
        })}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("reuse-provenance")).toBeTruthy());

    const link = screen.getByText("Open refresh research");
    expect(link.getAttribute("href")).toBe("/inv/inv-refresh-existing");
    expect(startInvestigationMock).not.toHaveBeenCalled();
    expect(recordSpawnRelationshipMock).not.toHaveBeenCalled();
  });

  it("restores the refresh child link from investigation summaries before localStorage", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    getTrajectoryMock.mockResolvedValue({ events: [] });
    render(
      <MasterMdViewer
        synthesis={synth({
          investigationId: "inv-parent",
          reuseProvenance: [
            {
              unitId: "unit-stale",
              sourceInvestigationId: "inv-source",
              score: 0.81,
              staleRefreshAdvisory: true,
            },
          ],
          compoundingStat: null,
        })}
        staleRefreshChildren={[
          investigationSummary({
            investigation_id: "inv-refresh-from-api",
            parent_investigation_id: "inv-parent",
            spawn_context:
              "stale-reuse-refresh unit_id=unit-stale source_investigation_id=inv-source",
          }),
        ]}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("reuse-provenance")).toBeTruthy());

    const link = screen.getByText("Open refresh research");
    expect(link.getAttribute("href")).toBe("/inv/inv-refresh-from-api");
    expect(screen.getByText("refresh research completed")).toBeTruthy();
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });

  it("shows a read-only refresh result excerpt from a completed child synthesis", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    getTrajectoryMock.mockResolvedValue({
      events: [
        {
          event_id: "evt-start",
          investigation_id: "inv-refresh-from-api",
          action_type: "investigation.start_requested",
          payload: { question: "Refresh?" },
          emitted_at: "2026-07-07T13:00:00Z",
        },
        {
          event_id: "evt-synth",
          investigation_id: "inv-refresh-from-api",
          action_type: "synthesize.delivered",
          payload: {
            thesis_summary: "Source claim remains current after checking the newer corpus.",
            thesis_components: [],
            implicit_recommendation: "proceed",
          },
          emitted_at: "2026-07-07T13:01:00Z",
        },
      ],
    });

    render(
      <MasterMdViewer
        synthesis={synth({
          investigationId: "inv-parent",
          reuseProvenance: [
            {
              unitId: "unit-stale",
              sourceInvestigationId: "inv-source",
              score: 0.81,
              staleRefreshAdvisory: true,
            },
          ],
          compoundingStat: null,
        })}
        staleRefreshChildren={[
          investigationSummary({
            investigation_id: "inv-refresh-from-api",
            parent_investigation_id: "inv-parent",
            spawn_context:
              "stale-reuse-refresh unit_id=unit-stale source_investigation_id=inv-source",
          }),
        ]}
      />,
    );
    await waitFor(() =>
      expect(
        screen.getByText(
          "refresh result: Source claim remains current after checking the newer corpus.",
        ),
      ).toBeTruthy(),
    );
    expect(getTrajectoryMock).toHaveBeenCalledWith("inv-refresh-from-api");
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });

  it("emits an acceptance event for a completed stale refresh child", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    postTypedEventMock.mockResolvedValue({
      event_id: "evt-accept",
      action_type: "stale_reuse.refresh.accepted",
    });
    getTrajectoryMock.mockResolvedValue({
      events: [
        {
          event_id: "evt-start",
          investigation_id: "inv-refresh-from-api",
          action_type: "investigation.start_requested",
          payload: { question: "Refresh?" },
          emitted_at: "2026-07-07T13:00:00Z",
        },
        {
          event_id: "evt-synth",
          investigation_id: "inv-refresh-from-api",
          action_type: "synthesize.delivered",
          payload: {
            thesis_summary: "Source claim remains current after checking the newer corpus.",
            thesis_components: [],
            implicit_recommendation: "proceed",
          },
          emitted_at: "2026-07-07T13:01:00Z",
        },
      ],
    });

    render(
      <MasterMdViewer
        synthesis={synth({
          investigationId: "inv-parent",
          reuseProvenance: [
            {
              unitId: "unit-stale",
              sourceInvestigationId: "inv-source",
              score: 0.81,
              staleRefreshAdvisory: true,
            },
          ],
          compoundingStat: null,
        })}
        staleRefreshChildren={[
          investigationSummary({
            investigation_id: "inv-refresh-from-api",
            parent_investigation_id: "inv-parent",
            spawn_context:
              "stale-reuse-refresh unit_id=unit-stale source_investigation_id=inv-source",
          }),
        ]}
      />,
    );

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Accept refresh result for prior insight unit-stale",
      }),
    );

    await waitFor(() =>
      expect(postTypedEventMock).toHaveBeenCalledWith({
        investigation_id: "inv-parent",
        role: "operator",
        policy_id: "operator-ui",
        payload: {
          action_type: "stale_reuse.refresh.accepted",
          unit_id: "unit-stale",
          source_investigation_id: "inv-source",
          refresh_investigation_id: "inv-refresh-from-api",
          status: "refreshed",
          summary: "Source claim remains current after checking the newer corpus.",
        },
      }),
    );
    expect(screen.getByText("refresh accepted")).toBeTruthy();
  });

  it("can confirm that a completed refresh child still leaves the prior insight stale", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    postTypedEventMock.mockResolvedValue({
      event_id: "evt-confirm-stale",
      action_type: "stale_reuse.refresh.accepted",
    });
    getTrajectoryMock.mockResolvedValue({
      events: [
        {
          event_id: "evt-synth",
          investigation_id: "inv-refresh-from-api",
          action_type: "synthesize.delivered",
          payload: {
            thesis_summary: "The refresh found newer evidence that contradicts the reused unit.",
            thesis_components: [],
            implicit_recommendation: "revise",
          },
          emitted_at: "2026-07-07T13:01:00Z",
        },
      ],
    });

    render(
      <MasterMdViewer
        synthesis={synth({
          investigationId: "inv-parent",
          reuseProvenance: [
            {
              unitId: "unit-stale",
              sourceInvestigationId: "inv-source",
              score: 0.81,
              staleRefreshAdvisory: true,
            },
          ],
          compoundingStat: null,
        })}
        staleRefreshChildren={[
          investigationSummary({
            investigation_id: "inv-refresh-from-api",
            parent_investigation_id: "inv-parent",
            spawn_context:
              "stale-reuse-refresh unit_id=unit-stale source_investigation_id=inv-source",
          }),
        ]}
      />,
    );

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Confirm stale result for prior insight unit-stale",
      }),
    );

    await waitFor(() =>
      expect(postTypedEventMock).toHaveBeenCalledWith(
        expect.objectContaining({
          payload: expect.objectContaining({
            action_type: "stale_reuse.refresh.accepted",
            status: "confirmed_stale",
            summary: "The refresh found newer evidence that contradicts the reused unit.",
          }),
        }),
      ),
    );
    expect(screen.getByText("stale confirmed")).toBeTruthy();
  });

  it("replays accepted refresh status labels when no backend child summary is present", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(
      <MasterMdViewer
        synthesis={synth({
          investigationId: "inv-parent",
          reuseProvenance: [
            {
              unitId: "unit-stale",
              sourceInvestigationId: "inv-source",
              score: 0.81,
              staleRefreshAdvisory: true,
              acceptedRefresh: {
                refreshInvestigationId: "inv-refresh-from-event",
                status: "dismissed",
                summary: "Operator dismissed this refresh result.",
              },
            },
          ],
          compoundingStat: null,
        })}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("reuse-provenance")).toBeTruthy());

    const link = screen.getByText("Open refresh research");
    expect(link.getAttribute("href")).toBe("/inv/inv-refresh-from-event");
    expect(screen.getByText("refresh dismissed")).toBeTruthy();
    expect(getTrajectoryMock).not.toHaveBeenCalled();
  });

  it("records a refreshed child synthesis as a promotion candidate with supporting chunks", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    postTypedEventMock.mockResolvedValue({
      event_id: "evt-promotion-candidate",
      action_type: "stale_reuse.refresh.promotion_candidate",
    });
    processStaleRefreshPromotionMock.mockResolvedValue({
      event_id: "evt-promotion-result",
      action_type: "stale_reuse.refresh.promotion_result",
      status: "deposited",
      reason: "ready",
      deposited_node_id: "node-refreshed",
      primary_chunk_id: "chunk-refresh-1",
      primary_source_document_id: "doc-refresh",
      supporting_chunk_ids: ["chunk-refresh-1", "chunk-refresh-2"],
      unresolved_chunk_ids: [],
      resolved_stale_edge_ids: ["edge-stale-personnel"],
    });
    getTrajectoryMock.mockResolvedValue({
      events: [
        {
          event_id: "evt-synth",
          investigation_id: "inv-refresh-from-api",
          action_type: "synthesize.delivered",
          payload: {
            thesis_summary: "Source claim remains current after checking the newer corpus.",
            thesis_components: [
              {
                claim: "The refreshed claim is supported.",
                confidence: "high",
                supporting_chunk_ids: ["chunk-refresh-1", "chunk-refresh-2"],
              },
              {
                claim: "The duplicate chunk should be deduplicated.",
                confidence: "medium",
                supporting_chunk_ids: ["chunk-refresh-1"],
              },
            ],
            implicit_recommendation: "proceed",
          },
          emitted_at: "2026-07-07T13:01:00Z",
        },
      ],
    });

    render(
      <MasterMdViewer
        synthesis={synth({
          investigationId: "inv-parent",
          reuseProvenance: [
            {
              unitId: "unit-stale",
              sourceInvestigationId: "inv-source",
              score: 0.81,
              staleRefreshAdvisory: true,
              staleAdvisoryEdgeIds: ["edge-stale-personnel"],
              acceptedRefresh: {
                refreshInvestigationId: "inv-refresh-from-api",
                status: "refreshed",
                summary: "Source claim remains current after checking the newer corpus.",
              },
            },
          ],
          compoundingStat: null,
        })}
        staleRefreshChildren={[
          investigationSummary({
            investigation_id: "inv-refresh-from-api",
            parent_investigation_id: "inv-parent",
            spawn_context:
              "stale-reuse-refresh unit_id=unit-stale source_investigation_id=inv-source",
          }),
        ]}
      />,
    );

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Prepare refreshed knowledge candidate for prior insight unit-stale",
      }),
    );

    await waitFor(() =>
      expect(postTypedEventMock).toHaveBeenCalledWith({
        investigation_id: "inv-parent",
        role: "operator",
        policy_id: "operator-ui",
        payload: {
          action_type: "stale_reuse.refresh.promotion_candidate",
          unit_id: "unit-stale",
          source_investigation_id: "inv-source",
          refresh_investigation_id: "inv-refresh-from-api",
          summary: "Source claim remains current after checking the newer corpus.",
          supporting_chunk_ids: ["chunk-refresh-1", "chunk-refresh-2"],
          stale_advisory_edge_ids: ["edge-stale-personnel"],
        },
      }),
    );
    await waitFor(() =>
      expect(processStaleRefreshPromotionMock).toHaveBeenCalledWith(
        "inv-parent",
        "evt-promotion-candidate",
      ),
    );
    expect(screen.getByText("promotion deposited").getAttribute("title")).toBe(
      "node node-refreshed · chunk chunk-refresh-1 · document doc-refresh · resolved stale edges edge-stale-personnel",
    );
  });

  it("replays promotion-candidate state without a backend child summary", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(
      <MasterMdViewer
        synthesis={synth({
          investigationId: "inv-parent",
          reuseProvenance: [
            {
              unitId: "unit-stale",
              sourceInvestigationId: "inv-source",
              score: 0.81,
              staleRefreshAdvisory: true,
              acceptedRefresh: {
                refreshInvestigationId: "inv-refresh-from-event",
                status: "refreshed",
                summary: "Operator accepted this refresh result.",
              },
              refreshPromotionCandidate: {
                refreshInvestigationId: "inv-refresh-from-event",
                summary: "Operator accepted this refresh result.",
                supportingChunkIds: ["chunk-refresh-1"],
              },
            },
          ],
          compoundingStat: null,
        })}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("reuse-provenance")).toBeTruthy());

    expect(screen.getByText("promotion candidate recorded")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /prepare refreshed/i })).toBeNull();
  });

  it("replays backend promotion-result state without a backend child summary", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(
      <MasterMdViewer
        synthesis={synth({
          investigationId: "inv-parent",
          reuseProvenance: [
            {
              unitId: "unit-stale",
              sourceInvestigationId: "inv-source",
              score: 0.81,
              staleRefreshAdvisory: true,
              acceptedRefresh: {
                refreshInvestigationId: "inv-refresh-from-event",
                status: "refreshed",
                summary: "Operator accepted this refresh result.",
              },
              refreshPromotionCandidate: {
                refreshInvestigationId: "inv-refresh-from-event",
                summary: "Operator accepted this refresh result.",
                supportingChunkIds: ["chunk-refresh-1"],
              },
              refreshPromotionResult: {
                refreshInvestigationId: "inv-refresh-from-event",
                status: "not_depositable",
                reason: "unresolved_supporting_chunks",
                depositedNodeId: null,
                primaryChunkId: null,
                primarySourceDocumentId: null,
                resolvedStaleEdgeIds: [],
                unresolvedChunkIds: ["missing-chunk"],
              },
            },
          ],
          compoundingStat: null,
        })}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("reuse-provenance")).toBeTruthy());

    expect(
      screen.getByText("promotion not depositable").getAttribute("title"),
    ).toBe("unresolved chunks missing-chunk");
    expect(screen.queryByText("promotion candidate recorded")).toBeNull();
    expect(getTrajectoryMock).not.toHaveBeenCalled();
  });

  it("renders the three exact numbers when a measurement is present (M4 seed-and-catch)", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    render(
      <MasterMdViewer
        synthesis={synth({
          reuseProvenance: [
            { unitId: "u1", sourceInvestigationId: "inv-a", score: 0.9 },
            { unitId: "u2", sourceInvestigationId: "inv-b", score: 0.8 },
            { unitId: "u3", sourceInvestigationId: "inv-c", score: 0.7 },
          ],
          // The synthetic measurement shape (the substrate emits none today).
          compoundingStat: { reused: 3, avoided: 2, fewerSources: 5 },
        })}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("reuse-provenance")).toBeTruthy());
    // All three exact numbers render in one declarative, sourced line.
    expect(
      screen.getByText("reused 3 insights · avoided 2 re-derivations · 5 fewer sources than cold"),
    ).toBeTruthy();
  });
});

describe("MasterMdViewer — review-due default-off byte-equivalence (SPR-08 M5)", () => {
  it("no claim span carries the review-due class or a review-due title on the default", async () => {
    getChunkMock.mockResolvedValue(chunk({ chunk_id: "c1" }));
    const { container } = render(<MasterMdViewer synthesis={synth()} />);
    await waitFor(() => expect(screen.getByText(/On Growth and Form/)).toBeTruthy());

    const claimSpans = container.querySelectorAll("[data-claim-id]");
    expect(claimSpans.length).toBeGreaterThan(0);
    for (const span of claimSpans) {
      expect(span.getAttribute("class") ?? "").not.toContain(REVIEW_DUE_CLASS);
      // The augmentation's only title source is its substrate cue ("Due …");
      // default-off declares none, so no claim span carries one.
      expect(span.getAttribute("title")).toBeNull();
    }
  });
});

describe("MasterMdViewer — artifact-export affordance (SPR-05 M5)", () => {
  // Claim-free fixtures: the export affordance is in the header and does not
  // depend on claims; empty components avoid the chunk-resolution augmentation
  // (which would call the unmocked getChunk) so we test the button in isolation.
  const exportSynth = (id: string | null): ParsedSynthesis =>
    synth({ synthesisId: id, components: [], chunkCitations: {} });

  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("shows the Export artifact action only when a synthesis id is present", () => {
    render(<MasterMdViewer synthesis={exportSynth("syn-1")} />);
    expect(screen.getByRole("button", { name: "HTML" })).toBeTruthy();
    cleanup();
    render(<MasterMdViewer synthesis={exportSynth(null)} />);
    expect(screen.queryByRole("button", { name: "HTML" })).toBeNull();
  });

  it("calls the artifact route and surfaces the SPECIFIC 403 reason", async () => {
    apiFetchMock.mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ reason: "owner withheld this synthesis" }),
    } as unknown as Response);

    render(<MasterMdViewer synthesis={exportSynth("syn-9")} />);
    fireEvent.click(screen.getByRole("button", { name: "HTML" }));

    await waitFor(() =>
      expect(screen.getByText(/owner withheld this synthesis/)).toBeTruthy(),
    );
    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    expect(String(apiFetchMock.mock.calls[0][0])).toContain(
      "/api/syntheses/syn-9/artifact?format=html",
    );
  });
});
