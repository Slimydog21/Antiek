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
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

import type { ChunkResponse } from "../../lib/api";
import type { ParsedSynthesis } from "../../lib/synthesisParser";

const { getChunkMock } = vi.hoisted(() => ({ getChunkMock: vi.fn() }));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, getChunk: getChunkMock };
});
// Workspace actions + toast are side-effectful; stub them so the render is
// pure. We assert on what the reader SEES, not on panel side effects.
vi.mock("../../workspace/actions", () => ({
  openNotebook: vi.fn(),
  openPdfPanel: vi.fn(),
}));
vi.mock("../../components/lemon/LemonToast", () => ({
  toast: { ok: vi.fn(), err: vi.fn() },
}));

import MasterMdViewer, { ClaimBlock, reviewDueDecorationsFor } from "./MasterMdViewer";
import { REVIEW_DUE_CLASS } from "../../reading-physics/augmentations/review-due";
import { anchorKey } from "../../reading-physics/facets/decorations";
import type { ClaimId } from "../../reading-physics/types";
import type { ParsedClaim } from "../../lib/synthesisParser";

afterEach(() => {
  cleanup();
  getChunkMock.mockReset();
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

function synth(over: Partial<ParsedSynthesis> = {}): ParsedSynthesis {
  return {
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
    ...over,
  };
}

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
