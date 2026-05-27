/**
 * review-due.compose.test.ts — SPR-08 M4: the agent-authored augmentation
 * passes the SAME un-relaxed gates and composes.
 *
 * The deliverable of this milestone is NOT the review-due feature; it is that an
 * augmentation written by an AGENT — from the AUTHORING_KIT alone, importing only
 * the contract — composes on ONE synthesis through the SPR-03/04 facets exactly
 * like a hand-written one, with no relaxation. review-due is a plain decoration
 * (geometry-independent), so it composes via the §5.1 range-union rule for free.
 *
 * This file proves (in isolation, headless):
 *   - M4 — review-due + Skim + SiteSee + marginalia ALL enabled on one fixture
 *     synthesis: review-due's `review-due` class AND Skim's role class merge on
 *     the SAME claim range as ONE resolved decoration (range UNION), SiteSee's
 *     tint + hover card render, and the margin note renders — proving the
 *     agent's module composes with the shipped roster without coupling;
 *   - M4 — the merge is ORDER-INDEPENDENT: shuffling the enable order yields a
 *     byte-identical resolved decoration set (deep-equal);
 *   - M4 — NO module imports another (PR-3), proved structurally by reading
 *     review-due.ts's text (it must import ONLY the contract — `../types`);
 *   - M4 — honest no-data: an EMPTY `dueClaims` → review-due declares nothing
 *     (no `review-due` class anywhere on the composed surface).
 *
 * It does NOT relax the guard or touch review-due.ts. review-due composes via the
 * union rule precisely because it is a plain decoration that knows nothing of the
 * other augmentations — that is the whole point.
 */
import { describe, expect, it } from "vitest";
import { createElement } from "react";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type {
  AnchoredWidgetComponents,
  ChunkId,
  ClaimId,
  ReadingContext,
  RenderContext,
  SubstrateReadApi,
} from "../types";
import { anchorKey } from "../facets/decorations";
import { collectAnchoredWidgets, collectDecorations } from "../registry";
import { resolveAnchoredWidgets } from "../facets/anchored-widgets";

import {
  REVIEW_DUE_CLASS,
  makeReviewDueAugmentation,
} from "./review-due";
import type { ReviewDueClaimView } from "./review-due";
import {
  SKIM_OBJECTIVE_CLASS,
  SKIM_RESULT_CLASS,
  makeSkimAugmentation,
} from "./skim";
import type { RhetoricalRoleView } from "./skim";
import {
  SITESEE_CITED_CLASS,
  makeSiteSeeAugmentation,
} from "./sitesee";
import type { SiteSeeSourceView } from "./sitesee";
import {
  makeMarginaliaAugmentation,
  reResolveNote,
} from "./marginalia/index";
import type { MarginNoteAuthored } from "./marginalia/index";

// ── substrate fixture (mirrors the shipped ChunkResponse shape, as the
//    marginalia compose test does — marginalia resolves its anchor by quote
//    against the substrate at declare time) ───────────────────────────────────

interface FixtureChunk {
  chunk_id: string;
  text: string;
  servable: boolean;
  servability: string | null;
}
function fakeSubstrate(chunks: FixtureChunk[]): SubstrateReadApi {
  const byId = new Map(chunks.map((c) => [c.chunk_id, c]));
  return {
    getChunk: (id: ChunkId) => {
      const c = byId.get(id);
      if (!c) return Promise.reject(new Error(`no chunk ${id}`));
      return Promise.resolve({
        chunk_id: c.chunk_id,
        text: c.servable ? c.text : "",
        section_path: null,
        token_count: 0,
        document_id: "doc1",
        document_title: "Doc",
        source_tier: 1,
        servable: c.servable,
        ip_holder_name: null,
        ip_holder_status: null,
        servability: c.servability,
      });
    },
  };
}
function ctxWith(chunks: FixtureChunk[]): ReadingContext {
  return {
    synthesis: {
      question: null,
      claims: chunks.map((c, i) => ({
        claimId: String(i + 1) as never,
        chunkIds: [c.chunk_id] as never,
      })),
    },
    layout: { resolve: () => null },
    substrate: fakeSubstrate(chunks),
  };
}
function viewMarkup(node: ReactNode): string {
  return renderToStaticMarkup(createElement("div", null, node));
}
function claimKey(id: string): string {
  return anchorKey({ kind: "claim", claimId: id as ClaimId });
}

const CHUNKS: FixtureChunk[] = [
  { chunk_id: "c1", text: "We aim to understand the rival's motive.", servable: true, servability: null },
  { chunk_id: "c2", text: "though only three years older, he had already left", servable: true, servability: null },
];

// ── M4 — the four-augmentation composition, with the agent's module in it ────

describe("composition — review-due + Skim + SiteSee + marginalia on ONE synthesis (M4, the deliverable)", () => {
  // A fixture synthesis with two claims:
  //   claim 1 — an OBJECTIVE that is ALSO due for review (the OVERLAP case:
  //             Skim's objective color + review-due's cue land on the SAME
  //             claim range);
  //   claim 2 — a RESULT that is ALSO a cited source (Skim's result color +
  //             SiteSee's cited tint; NOT due for review).
  const roles: RhetoricalRoleView[] = [
    { claimId: "1", role: "objective" },
    { claimId: "2", role: "result" },
  ];
  const sources: SiteSeeSourceView[] = [
    { representativeChunkId: "c2", markerClaimId: "2", state: "cited", servable: true, title: "On Composition", ipHolderName: "MIT Press" },
  ];
  // review-due marks claim 1 (with a substrate-resolved cue label).
  const dueClaims: ReviewDueClaimView[] = [
    { claimId: "1", dueLabel: "Due today" },
  ];

  it("review-due's class AND Skim's role class merge on the SAME claim range as ONE resolved decoration", async () => {
    const ctx = ctxWith(CHUNKS);
    const reviewDue = makeReviewDueAugmentation(dueClaims);
    const skim = makeSkimAugmentation(roles);
    const sitesee = makeSiteSeeAugmentation(sources);
    // Author + resolve a margin note so all four facets are genuinely live.
    const authored: MarginNoteAuthored = {
      id: "n1",
      anchorQuote: "though only three years older",
      comment: "This callback echoes the opening line.",
      clip: null,
    };
    const note = await reResolveNote(authored, ctx);
    expect(note.resolution.kind).toBe("match");
    const marginalia = makeMarginaliaAugmentation([note]);

    const all = [reviewDue, skim, sitesee, marginalia];

    // ── DECORATIONS facet — the headline merge ──
    const decos = collectDecorations(all, ctx);
    const byKey = new Map(decos.map((d) => [d.key, d]));

    // THE OVERLAP — claim 1 is an OBJECTIVE *and* due for review: ONE resolved
    // decoration carries BOTH Skim's objective class AND review-due's class.
    const c1 = byKey.get(claimKey("1"));
    expect(c1).toBeDefined();
    expect(c1!.classNames).toContain(SKIM_OBJECTIVE_CLASS); // Skim contributed
    expect(c1!.classNames).toContain(REVIEW_DUE_CLASS); // review-due contributed
    // Both, merged into a single range — sorted union (order-independent).
    expect(c1!.classNames).toEqual(
      [SKIM_OBJECTIVE_CLASS, REVIEW_DUE_CLASS].sort(),
    );
    // Exactly ONE resolved decoration for claim 1's range (the union, not two).
    expect(decos.filter((d) => d.key === claimKey("1"))).toHaveLength(1);
    // review-due's substrate-resolved cue ("Due today") and Skim's role label
    // ("Objective") BOTH ride the §5.1 title-join — the SET of declared titles,
    // sorted, joined by " · ". So the merge composes the TITLE dimension too,
    // not just the class set, deterministically and order-independently.
    expect(c1!.title).toBe(["Due today", "Objective"].sort().join(" · "));
    expect(c1!.title).toContain("Due today"); // review-due's cue is present …
    // … as a real fragment, no phantom `undefined` (the title-omit kit gap).
    expect(c1!.title).not.toContain("undefined");

    // claim 2 is a RESULT + a cited source, NOT due for review — Skim's result
    // class + SiteSee's cited tint merge, but review-due fabricated nothing.
    const c2 = byKey.get(claimKey("2"));
    expect(c2!.classNames).toContain(SKIM_RESULT_CLASS);
    expect(c2!.classNames).toContain(SITESEE_CITED_CLASS);
    expect(c2!.classNames).not.toContain(REVIEW_DUE_CLASS);

    // ── ANCHORED-WIDGETS facet — SiteSee's hover card + the margin note ──
    // (review-due declares no widget; it composes on the decorations facet only.)
    const plan = collectAnchoredWidgets(all, ctx);
    const ids = plan.all.map((p) => p.widget.id).sort();
    expect(ids).toContain("sitesee-hovercard:c2");
    expect(ids).toContain("marginalia:n1");

    // SiteSee's card + the margin note RENDER their bounded data (the facet
    // composes with review-due present, neither knowing the other exists).
    const components: AnchoredWidgetComponents = {
      SiteSeeHoverCard: ({ title, ipHolderName }) =>
        createElement(
          "div",
          null,
          createElement("span", null, title),
          ipHolderName ? createElement("em", null, ipHolderName) : null,
        ),
      MarginNote: ({ comment, excerpt }) =>
        createElement(
          "aside",
          null,
          createElement("blockquote", null, excerpt),
          createElement("p", null, comment),
        ),
    };
    const renderCtx: RenderContext = { pass: "main", layout: { resolve: () => null }, components };
    const widgets = plan.all.map((p) => p.widget);
    const enacted = resolveAnchoredWidgets(widgets, renderCtx.layout);
    const html = enacted.map((e) => viewMarkup(e.widget.render(e.rect, renderCtx))).join("");
    expect(html).toContain("On Composition"); // SiteSee's card
    expect(html).toContain("MIT Press");
    expect(html).toContain("This callback echoes the opening line."); // the note
    expect(html).toContain("though only three years older"); // its anchored excerpt
  });

  it("the merge is ORDER-INDEPENDENT — shuffling enable order is deep-equal", async () => {
    const ctx = ctxWith(CHUNKS);
    const reviewDue = makeReviewDueAugmentation(dueClaims);
    const skim = makeSkimAugmentation(roles);
    const sitesee = makeSiteSeeAugmentation(sources);
    const note = await reResolveNote(
      { id: "n1", anchorQuote: "though only three years older", comment: "x", clip: null },
      ctx,
    );
    const marginalia = makeMarginaliaAugmentation([note]);

    // The exact roster, two different enable orders. The §5.1 combine is a
    // function of the SET of declarations, never of declaration order — so the
    // resolved decoration set is byte-identical regardless of order.
    const forward = collectDecorations([reviewDue, skim, sitesee, marginalia], ctx);
    const shuffled = collectDecorations([sitesee, marginalia, reviewDue, skim], ctx);
    expect(shuffled).toEqual(forward);

    // And the overlap on claim 1 carries BOTH classes in either order.
    const c1Forward = forward.find((d) => d.key === claimKey("1"))!;
    expect(c1Forward.classNames).toEqual([SKIM_OBJECTIVE_CLASS, REVIEW_DUE_CLASS].sort());
  });

  it("NO module imports another (PR-3) — review-due imports ONLY the contract", async () => {
    const fs = await import("node:fs/promises");
    const dir = "src/reading-physics/augmentations";
    const reviewDue = await fs.readFile(`${dir}/review-due.ts`, "utf8");

    // review-due imports NONE of the sibling augmentations — it composes only
    // through the named facets (PR-3). Pinned for the SPR-08 roster.
    expect(reviewDue).not.toMatch(/from\s+["'][^"']*\/skim["']/);
    expect(reviewDue).not.toMatch(/from\s+["'][^"']*\/sitesee["']/);
    expect(reviewDue).not.toMatch(/from\s+["'][^"']*\/marginalia/);
    expect(reviewDue).not.toMatch(/from\s+["'][^"']*\/quality-cue["']/);
    expect(reviewDue).not.toMatch(/from\s+["'][^"']*\/servability["']/);
    expect(reviewDue).not.toMatch(/from\s+["'][^"']*\/ip-holder["']/);

    // The agent module's ONLY import is the contract — `../types` (PR-8). Every
    // `from "…"` in the module text must resolve to `../types`. (A static pin of
    // the PR-8 allowlist for the agent-authored module; the CI guard enforces it
    // tree-wide.)
    const fromTargets = [...reviewDue.matchAll(/from\s+["']([^"']+)["']/g)].map((m) => m[1]);
    expect(fromTargets.length).toBeGreaterThan(0);
    for (const target of fromTargets) {
      expect(target).toBe("../types");
    }

    // And the shipped siblings don't reach for review-due either.
    const skim = await fs.readFile(`${dir}/skim.ts`, "utf8");
    const sitesee = await fs.readFile(`${dir}/sitesee.ts`, "utf8");
    expect(skim).not.toMatch(/review-due/);
    expect(sitesee).not.toMatch(/review-due/);
  });
});

// ── M4 — honest no-data ──────────────────────────────────────────────────────

describe("honest no-data (M4) — review-due fabricates nothing", () => {
  it("an EMPTY dueClaims → review-due declares nothing (no review-due class anywhere)", () => {
    const ctx = ctxWith(CHUNKS);
    const reviewDue = makeReviewDueAugmentation([]); // no review state resolved
    const skim = makeSkimAugmentation([
      { claimId: "1", role: "objective" },
      { claimId: "2", role: "result" },
    ]);
    const sitesee = makeSiteSeeAugmentation([
      { representativeChunkId: "c2", markerClaimId: "2", state: "cited", servable: true, title: "T", ipHolderName: null },
    ]);

    const decos = collectDecorations([reviewDue, skim, sitesee], ctx);
    // The other augmentations still light up (the surface isn't empty) …
    expect(decos.some((d) => d.classNames.includes(SKIM_OBJECTIVE_CLASS))).toBe(true);
    // … but NO review-due class appears anywhere — empty dueClaims declared
    // nothing. No guessed cue (the honest dormant-correct state).
    expect(decos.every((d) => !d.classNames.includes(REVIEW_DUE_CLASS))).toBe(true);
  });

  it("review-due ALONE with empty dueClaims resolves to an empty decoration set", () => {
    const ctx = ctxWith(CHUNKS);
    expect(collectDecorations([makeReviewDueAugmentation([])], ctx)).toEqual([]);
  });
});
