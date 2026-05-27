/**
 * skim-sitesee.compose.test.ts — SPR-06: THE composition proof.
 *
 * The deliverable of this sprint is NOT the two features; it is that two
 * INDEPENDENT augmentations from two different ideas (Skim's rhetorical-role
 * colors, SiteSee's citation tints + hover card) compose on ONE synthesis
 * through the SPR-03/04 facets — neither importing the other, both grounded in
 * the substrate — proving the physics accumulates new ideas without coupling.
 *
 * This file proves (in isolation, headless):
 *   - M3 — BOTH enabled on one fixture synthesis: Skim's backgrounds AND
 *     SiteSee's tints (decorations facet) AND SiteSee's hover card
 *     (anchored-widgets facet) are ALL present and correctly merged;
 *   - M3 — NEITHER module imports the other (PR-3), proved structurally;
 *   - rigor #3 / overlap determinism — a cited "result" sentence (Skim's role
 *     color and SiteSee's tint land on the SAME claim range) merges to one
 *     resolved decoration carrying BOTH classes, deterministically, regardless
 *     of enable order;
 *   - §9.0 — a non-servable cited source's hover card shows ONLY bounded
 *     metadata (title), never the owner or any body;
 *   - M5 — honest no-data: a synthesis with no resolved roles → Skim renders
 *     nothing; a paper with no citation history → SiteSee tints nothing.
 */
import { describe, expect, it } from "vitest";
import { createElement } from "react";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type {
  Anchor,
  AnchoredWidgetComponents,
  ClaimId,
  ReadingContext,
  RenderContext,
} from "./types";
import { anchorKey } from "./facets/decorations";
import {
  SKIM_OBJECTIVE_CLASS,
  SKIM_RESULT_CLASS,
  makeSkimAugmentation,
} from "./augmentations/skim";
import type { RhetoricalRoleView } from "./augmentations/skim";
import {
  SITESEE_CITED_CLASS,
  SITESEE_READ_CLASS,
  makeSiteSeeAugmentation,
} from "./augmentations/sitesee";
import type { SiteSeeSourceView } from "./augmentations/sitesee";
import { collectAnchoredWidgets, collectDecorations } from "./registry";
import { resolveAnchoredWidgets } from "./facets/anchored-widgets";

// ── headless render helpers (mirror anchored-widgets.test.ts) ───────────────

const STUB_CTX: ReadingContext = {
  synthesis: { question: null, claims: [] },
  layout: { resolve: () => null },
  substrate: {
    getChunk: () => Promise.reject(new Error("not wired in the engine test")),
  },
};

function claimAnchor(id: string): Anchor {
  return { kind: "claim", claimId: id as ClaimId };
}
function viewMarkup(node: ReactNode): string {
  return renderToStaticMarkup(createElement("div", null, node));
}

// ── M3 — the headline composition proof: BOTH present + merged ──────────────

describe("composition — Skim + SiteSee on ONE synthesis (M3, the deliverable)", () => {
  // A fixture synthesis with three claims:
  //   claim 1 — an OBJECTIVE, no citation history (Skim colors it; SiteSee
  //             leaves it untinted);
  //   claim 2 — a RESULT that is ALSO a cited source the reader has cited
  //             (the OVERLAP case: Skim's result color + SiteSee's cited tint
  //             land on the SAME claim range);
  //   claim 3 — an "other" claim (Skim leaves it; SiteSee tints its source as
  //             "read").
  const roles: RhetoricalRoleView[] = [
    { claimId: "1", role: "objective" },
    { claimId: "2", role: "result" },
    { claimId: "3", role: "other" },
  ];
  const sources: SiteSeeSourceView[] = [
    // claim 2's cited source — tint lands on claim 2 (the overlap).
    {
      representativeChunkId: "c2",
      markerClaimId: "2",
      state: "cited",
      servable: true,
      title: "On Composition",
      ipHolderName: "MIT Press",
    },
    // claim 3's read source — tint lands on claim 3.
    {
      representativeChunkId: "c3",
      markerClaimId: "3",
      state: "read",
      servable: true,
      title: "A Read Paper",
      ipHolderName: null,
    },
  ];

  it("BOTH augmentations' decorations are present and merged (Skim colors + SiteSee tints)", () => {
    const skim = makeSkimAugmentation(roles);
    const sitesee = makeSiteSeeAugmentation(sources);

    const out = collectDecorations([skim, sitesee], STUB_CTX);
    const byKey = new Map(out.map((d) => [d.key, d]));

    // Skim's OBJECTIVE color is present on claim 1 (Skim-only, no tint there).
    const c1 = byKey.get(anchorKey(claimAnchor("1")));
    expect(c1?.classNames).toEqual([SKIM_OBJECTIVE_CLASS]);

    // THE OVERLAP — claim 2 is a RESULT *and* a cited source: ONE resolved
    // decoration carries BOTH Skim's result class AND SiteSee's cited tint.
    const c2 = byKey.get(anchorKey(claimAnchor("2")));
    expect(c2).toBeDefined();
    expect(c2!.classNames).toContain(SKIM_RESULT_CLASS); // Skim contributed
    expect(c2!.classNames).toContain(SITESEE_CITED_CLASS); // SiteSee contributed
    // Both, merged — order-independent sorted union.
    expect(c2!.classNames).toEqual(
      [SKIM_RESULT_CLASS, SITESEE_CITED_CLASS].sort(),
    );

    // claim 3 is "other" for Skim (no color) but READ for SiteSee (tinted):
    // only SiteSee's tint is present — Skim fabricated nothing.
    const c3 = byKey.get(anchorKey(claimAnchor("3")));
    expect(c3?.classNames).toEqual([SITESEE_READ_CLASS]);
  });

  it("SiteSee's hover card is present on the anchored-widgets facet (BOTH facets used)", () => {
    const skim = makeSkimAugmentation(roles);
    const sitesee = makeSiteSeeAugmentation(sources);

    // The composition uses TWO facets at once: decorations (above) AND
    // anchored-widgets (SiteSee's hover card). Skim contributes no widget, so
    // the widget plan is exactly SiteSee's cards — proving the two facets
    // compose on one pass without either augmentation knowing the other.
    const plan = collectAnchoredWidgets([skim, sitesee], STUB_CTX);
    const cardIds = plan.all.map((p) => p.widget.id).sort();
    expect(cardIds).toEqual([
      "sitesee-hovercard:c2",
      "sitesee-hovercard:c3",
    ]);

    // The card actually RENDERS its bounded metadata through the surface
    // component (the de-overlap places it; SPR-04 enact resolves the rect).
    const components: AnchoredWidgetComponents = {
      SiteSeeHoverCard: ({ title, ipHolderName, state }) =>
        createElement(
          "div",
          null,
          createElement("span", null, title),
          ipHolderName ? createElement("em", null, ipHolderName) : null,
          createElement("small", null, state),
        ),
    };
    const ctx: RenderContext = { pass: "main", layout: { resolve: () => null }, components };
    const widgets = plan.all.map((p) => p.widget);
    const enacted = resolveAnchoredWidgets(widgets, ctx.layout);
    const html = enacted.map((e) => viewMarkup(e.widget.render(e.rect, ctx))).join("");
    expect(html).toContain("On Composition"); // claim 2's card
    expect(html).toContain("MIT Press"); // servable ⇒ owner shown
    expect(html).toContain("A Read Paper"); // claim 3's card
  });

  it("NEITHER module imports the other (PR-3) — proved by their module text", async () => {
    const fs = await import("node:fs/promises");
    const dir = "src/reading-physics/augmentations";
    const skim = await fs.readFile(`${dir}/skim.ts`, "utf8");
    const sitesee = await fs.readFile(`${dir}/sitesee.ts`, "utf8");
    // Skim does not import SiteSee, and SiteSee does not import Skim — they
    // meet ONLY at the named facets. (The CI guard enforces this tree-wide;
    // this pins it for the SPR-06 pair.)
    expect(skim).not.toMatch(/from\s+["'].*sitesee["']/);
    expect(sitesee).not.toMatch(/from\s+["'].*skim["']/);
  });
});

// ── overlap determinism (rigor #3) ──────────────────────────────────────────

describe("overlap determinism — a cited 'result' sentence (rigor #3)", () => {
  // Skim colors claim 2 a RESULT; SiteSee tints claim 2 as CITED. They overlap
  // on the EXACT same claim range. The merge must be deterministic and
  // independent of enable order.
  const skim = makeSkimAugmentation([{ claimId: "2", role: "result" }]);
  const sitesee = makeSiteSeeAugmentation([
    { representativeChunkId: "c2", markerClaimId: "2", state: "cited", servable: true, title: "T", ipHolderName: null },
  ]);

  it("forward and reverse enable order resolve byte-identically", () => {
    const forward = collectDecorations([skim, sitesee], STUB_CTX);
    const reverse = collectDecorations([sitesee, skim], STUB_CTX);
    expect(reverse).toEqual(forward);
  });

  it("the overlapped range carries BOTH classes, sorted (a single resolved decoration)", () => {
    const out = collectDecorations([skim, sitesee], STUB_CTX);
    const c2 = out.find((d) => d.key === anchorKey(claimAnchor("2")));
    // Exactly ONE resolved decoration for the range (the union), not two.
    expect(out.filter((d) => d.key === anchorKey(claimAnchor("2")))).toHaveLength(1);
    expect(c2!.classNames).toEqual([SKIM_RESULT_CLASS, SITESEE_CITED_CLASS].sort());
  });

  it("both decorating the EXACT same range is a deterministic union (no winner-takes-all)", () => {
    // Both anchor to claim 2; both apply. Neither suppresses the other — the
    // §5.1 rule is union, not precedence. (Cross-FACET visual stacking is a
    // z-order the surface owns; within the decorations facet both classes paint.)
    const out = collectDecorations([skim, sitesee], STUB_CTX);
    const c2 = out.find((d) => d.key === anchorKey(claimAnchor("2")))!;
    expect(c2.classNames).toContain(SKIM_RESULT_CLASS);
    expect(c2.classNames).toContain(SITESEE_CITED_CLASS);
  });
});

// ── §9.0 — non-servable cited source: bounded metadata only ─────────────────

describe("§9.0 — a non-servable cited source's hover card shows only bounded metadata", () => {
  const WITHHELD_OWNER = "Penguin Random House";
  // A non-servable cited source. Per §9.0 the substrate already withheld the
  // owner (ipHolderName = null) AND the body; the augmentation must pass ONLY
  // the title to the card, never the owner, never any body.
  const sitesee = makeSiteSeeAugmentation([
    {
      representativeChunkId: "c9",
      markerClaimId: "2",
      state: "cited",
      servable: false,
      title: "A Restricted Source",
      // The augmentation receives null here (the endpoint withholds it). Even
      // if a caller mistakenly passed an owner, the augmentation drops it for a
      // non-servable source — asserted below via a deliberately-populated case.
      ipHolderName: WITHHELD_OWNER, // deliberately set to PROVE it is dropped.
    },
  ]);

  it("the card renders the title but NOT the owner or any body (gate reused, not overridden)", () => {
    const plan = collectAnchoredWidgets([sitesee], STUB_CTX);
    const components: AnchoredWidgetComponents = {
      // The surface card would only show an owner if the augmentation passed
      // one. We render whatever the augmentation passes, to prove what it does.
      SiteSeeHoverCard: ({ title, servable, ipHolderName, state }) =>
        createElement(
          "div",
          null,
          createElement("span", null, title),
          createElement("small", { "data-servable": String(servable) }, state),
          ipHolderName ? createElement("em", null, ipHolderName) : null,
        ),
    };
    const ctx: RenderContext = { pass: "main", layout: { resolve: () => null }, components };
    const widgets = plan.all.map((p) => p.widget);
    const enacted = resolveAnchoredWidgets(widgets, ctx.layout);
    const html = enacted.map((e) => viewMarkup(e.widget.render(e.rect, ctx))).join("");

    expect(html).toContain("A Restricted Source"); // bounded title is shown …
    expect(html).toContain(`data-servable="false"`); // … the §9.0 verdict carried …
    expect(html).not.toContain(WITHHELD_OWNER); // … but the OWNER is NOT leaked.
  });
});

// ── M5 — honest no-data states ──────────────────────────────────────────────

describe("honest no-data states (M5) — nothing fabricated", () => {
  it("a synthesis with NO rhetorical classification → Skim renders nothing", () => {
    // Empty role view (no synthesis structure resolved a role): Skim declares
    // zero decorations. No guessed colors.
    const skim = makeSkimAugmentation([]);
    expect(collectDecorations([skim], STUB_CTX)).toEqual([]);
  });

  it("every claim is 'other' → Skim still declares nothing (no fabricated color)", () => {
    const skim = makeSkimAugmentation([
      { claimId: "1", role: "other" },
      { claimId: "2", role: "other" },
    ]);
    expect(collectDecorations([skim], STUB_CTX)).toEqual([]);
  });

  it("a paper with NO citation history → SiteSee tints nothing", () => {
    // Every source is "unseen" (no read/saved/cited history). SiteSee declares
    // NO tint decoration — only the hover cards (the source details still
    // exist, just no fabricated tint).
    const sitesee = makeSiteSeeAugmentation([
      { representativeChunkId: "c1", state: "unseen", servable: true, title: "T1", ipHolderName: null },
      { representativeChunkId: "c2", state: "unseen", servable: true, title: "T2", ipHolderName: null },
    ]);
    // No tint decorations at all.
    expect(collectDecorations([sitesee], STUB_CTX)).toEqual([]);
    // But the hover cards are still declared (unseen ≠ "no card").
    const plan = collectAnchoredWidgets([sitesee], STUB_CTX);
    expect(plan.all.map((p) => p.widget.id).sort()).toEqual([
      "sitesee-hovercard:c1",
      "sitesee-hovercard:c2",
    ]);
  });

  it("BOTH no-data together → an empty surface (no decorations from either)", () => {
    const skim = makeSkimAugmentation([{ claimId: "1", role: "other" }]);
    const sitesee = makeSiteSeeAugmentation([
      { representativeChunkId: "c1", state: "unseen", servable: false, title: null, ipHolderName: null },
    ]);
    expect(collectDecorations([skim, sitesee], STUB_CTX)).toEqual([]);
  });
});
