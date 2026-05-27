/**
 * marginalia.compose.test.ts — SPR-07 M5 (+ M2, M3, M4): THE composition proof.
 *
 * The deliverable: voice-anchored marginalia composes with Skim, SiteSee, AND
 * QualityCue on ONE synthesis through the SPR-03/04 facets — neither importing
 * the other — proving the physics accumulates the talk's own demo without
 * coupling. This file proves:
 *   - M5 — all four enabled on one fixture: Skim's colors + SiteSee's tints
 *     (decorations facet) AND SiteSee's hover card + QualityCue's cue + the
 *     margin note (anchored-widgets facet) all render; the margin note
 *     DE-OVERLAPS the others (its own `left-gutter` lane); NO module imports
 *     another (the SPR-03 guard's PR-3, pinned structurally here);
 *   - M2 — the note declares an anchored widget at the RESOLVED passage anchor
 *     and renders the surface-supplied MarginNote with §9.0-gated props;
 *   - M3 — a note with NO clip works fully; a clip with a FAILED transcript
 *     renders the honest marker, never a fabricated transcript;
 *   - M4 — copying a note carries its quote-anchor; moving the underlying
 *     content re-resolves the anchor BY QUOTE (not a stale coordinate);
 *   - M6 — a withheld (non-servable) target anchors to the bounded chunk surface
 *     and the note's excerpt is null (no body leaked).
 */
import { describe, expect, it } from "vitest";
import { createElement } from "react";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type {
  AnchoredWidgetComponents,
  ChunkId,
  ReadingContext,
  RenderContext,
  SubstrateReadApi,
} from "../../types";
import { anchorKey } from "../../facets/decorations";
import { collectAnchoredWidgets, collectDecorations } from "../../registry";
import { resolveAnchoredWidgets } from "../../facets/anchored-widgets";

import {
  SKIM_OBJECTIVE_CLASS,
  SKIM_RESULT_CLASS,
  makeSkimAugmentation,
} from "../skim";
import type { RhetoricalRoleView } from "../skim";
import { SITESEE_CITED_CLASS, makeSiteSeeAugmentation } from "../sitesee";
import type { SiteSeeSourceView } from "../sitesee";
import { makeQualityCueAugmentation } from "../quality-cue";
import {
  makeMarginaliaAugmentation,
  reResolveNote,
  copyNote,
  noteAnchor,
} from "./index";
import type { MarginNoteAuthored, ResolvedMarginNote } from "./index";

// ── substrate fixture (mirrors the shipped ChunkResponse shape) ─────────────

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

const CHUNKS: FixtureChunk[] = [
  { chunk_id: "c1", text: "We aim to understand the rival's motive.", servable: true, servability: null },
  { chunk_id: "c2", text: "though only three years older, he had already left", servable: true, servability: null },
];

// ── M5 — the four-augmentation composition ──────────────────────────────────

describe("composition — Marginalia + Skim + SiteSee + QualityCue on ONE synthesis (M5)", () => {
  const roles: RhetoricalRoleView[] = [
    { claimId: "1", role: "objective" },
    { claimId: "2", role: "result" },
  ];
  const sources: SiteSeeSourceView[] = [
    { representativeChunkId: "c2", markerClaimId: "2", state: "cited", servable: true, title: "On Composition", ipHolderName: "MIT Press" },
  ];

  it("all four augmentations' contributions render; the margin note de-overlaps the others", async () => {
    const ctx = ctxWith(CHUNKS);
    // Author + resolve a margin note anchored to the talk's own quote.
    const authored: MarginNoteAuthored = {
      id: "n1",
      anchorQuote: "though only three years older",
      comment: "This callback echoes the opening line.",
      clip: null,
    };
    const note = await reResolveNote(authored, ctx);
    expect(note.resolution.kind).toBe("match"); // resolved to a unique passage

    const skim = makeSkimAugmentation(roles);
    const sitesee = makeSiteSeeAugmentation(sources);
    const quality = makeQualityCueAugmentation({
      composite: 0.8, voiceStyle: null, conviction: null, citationDensity: null, constraintCompliance: null,
    });
    const marginalia = makeMarginaliaAugmentation([note]);
    const all = [skim, sitesee, quality, marginalia];

    // DECORATIONS facet — Skim's colors + SiteSee's cited tint both present.
    const decos = collectDecorations(all, ctx);
    const byKey = new Map(decos.map((d) => [d.key, d]));
    expect(byKey.get(anchorKey({ kind: "claim", claimId: "1" as never }))?.classNames)
      .toEqual([SKIM_OBJECTIVE_CLASS]);
    const c2 = byKey.get(anchorKey({ kind: "claim", claimId: "2" as never }));
    expect(c2!.classNames).toContain(SKIM_RESULT_CLASS);
    expect(c2!.classNames).toContain(SITESEE_CITED_CLASS);

    // ANCHORED-WIDGETS facet — SiteSee card + QualityCue cue + the margin note.
    const plan = collectAnchoredWidgets(all, ctx);
    const ids = plan.all.map((p) => p.widget.id).sort();
    expect(ids).toContain("sitesee-hovercard:c2");
    expect(ids).toContain("quality-cue");
    expect(ids).toContain("marginalia:n1");

    // DE-OVERLAP — the margin note lives in its OWN lane (`left-gutter`), so it
    // never collides with SiteSee (`inline-end`) or QualityCue (`right-gutter`).
    const lanesById = new Map(plan.all.map((p) => [p.widget.id, p.lane]));
    expect(lanesById.get("marginalia:n1")).toBe("left-gutter");
    expect(lanesById.get("sitesee-hovercard:c2")).toBe("inline-end");
    expect(lanesById.get("quality-cue")).toBe("right-gutter");
    // The plan groups by lane → the four widgets occupy three distinct lanes,
    // each de-overlapping group resolved independently (no cross-lane collision).
    const laneGroups = new Set(plan.byLane.map((g) => g.lane));
    expect(laneGroups.has("left-gutter")).toBe(true);

    // The margin note RENDERS its bounded data through the surface component (M2).
    const components: AnchoredWidgetComponents = {
      MarginNote: ({ comment, excerpt, servable }) =>
        createElement(
          "aside",
          { "data-servable": String(servable) },
          createElement("blockquote", null, excerpt),
          createElement("p", null, comment),
        ),
    };
    const renderCtx: RenderContext = { pass: "main", layout: { resolve: () => null }, components };
    const widgets = plan.all.map((p) => p.widget);
    const enacted = resolveAnchoredWidgets(widgets, renderCtx.layout);
    const html = enacted.map((e) => viewMarkup(e.widget.render(e.rect, renderCtx))).join("");
    expect(html).toContain("This callback echoes the opening line."); // the comment
    expect(html).toContain("though only three years older"); // the anchored excerpt
  });

  it("NO module imports another (PR-3) — pinned by module text for the SPR-07 quartet", async () => {
    const fs = await import("node:fs/promises");
    const aug = "src/reading-physics/augmentations";
    const idx = await fs.readFile(`${aug}/marginalia/index.ts`, "utf8");
    // Marginalia imports NONE of the sibling augmentations (it composes only
    // through the facets). It DOES import its OWN package's resolve-quote/voice
    // (same folder = one augmentation), which is not a sibling import.
    expect(idx).not.toMatch(/from\s+["'][^"']*\/skim["']/);
    expect(idx).not.toMatch(/from\s+["'][^"']*\/sitesee["']/);
    expect(idx).not.toMatch(/from\s+["'][^"']*\/quality-cue["']/);
    // The others don't reach for marginalia either.
    const sitesee = await fs.readFile(`${aug}/sitesee.ts`, "utf8");
    const skim = await fs.readFile(`${aug}/skim.ts`, "utf8");
    expect(sitesee).not.toMatch(/marginalia/);
    expect(skim).not.toMatch(/marginalia/);
  });
});

// ── M2 — placement (anchored at the resolved passage) ───────────────────────

describe("margin-note widget placement (M2)", () => {
  it("a unique-match note declares ONE widget at the resolved passage anchor", async () => {
    const ctx = ctxWith(CHUNKS);
    const note = await reResolveNote(
      { id: "n1", anchorQuote: "though only three years older", comment: "x" },
      ctx,
    );
    const plan = collectAnchoredWidgets([makeMarginaliaAugmentation([note])], ctx);
    expect(plan.all).toHaveLength(1);
    const w = plan.all[0].widget;
    expect(w.id).toBe("marginalia:n1");
    expect(w.anchor.kind).toBe("passage"); // PR-4: a passage anchor, not a pixel
    if (w.anchor.kind === "passage") expect(w.anchor.chunkId).toBe("c2");
  });

  it("a no-match / ambiguous note declares NO widget (never silently anchored)", async () => {
    const ctx = ctxWith(CHUNKS);
    const noMatch = await reResolveNote(
      { id: "nm", anchorQuote: "not present anywhere", comment: "x" },
      ctx,
    );
    expect(noMatch.resolution.kind).toBe("no-match");
    expect(noteAnchor(noMatch.resolution)).toBeNull();
    const plan = collectAnchoredWidgets([makeMarginaliaAugmentation([noMatch])], ctx);
    expect(plan.all).toHaveLength(0); // no widget — honest, not a wrong anchor
  });
});

// ── M3 — voice optional + the failed/absent-transcript case ─────────────────

describe("optional voice clip (M3)", () => {
  const components: AnchoredWidgetComponents = {
    MarginNote: ({ comment, transcript, audioRef }) =>
      createElement(
        "aside",
        { "data-clip": audioRef ?? "none" },
        createElement("p", null, comment),
        transcript ? createElement("em", { "data-kind": "transcript" }, transcript) : null,
      ),
  };
  const renderCtx: RenderContext = { pass: "main", layout: { resolve: () => null }, components };

  async function renderNote(note: ResolvedMarginNote): Promise<string> {
    const plan = collectAnchoredWidgets([makeMarginaliaAugmentation([note])], ctxWith(CHUNKS));
    const enacted = resolveAnchoredWidgets(plan.all.map((p) => p.widget), renderCtx.layout);
    return enacted.map((e) => viewMarkup(e.widget.render(e.rect, renderCtx))).join("");
  }

  it("a note with NO clip works fully (voice is optional)", async () => {
    const ctx = ctxWith(CHUNKS);
    const note = await reResolveNote(
      { id: "n1", anchorQuote: "though only three years older", comment: "no clip here", clip: null },
      ctx,
    );
    const html = await renderNote(note);
    expect(html).toContain("no clip here");
    expect(html).toContain(`data-clip="none"`); // no audio ref
    expect(html).not.toContain(`data-kind="transcript"`); // no transcript element
  });

  it("a clip with a CONFIRMED transcript surfaces it (text is the data, PR-2)", async () => {
    const ctx = ctxWith(CHUNKS);
    const note = await reResolveNote(
      {
        id: "n2",
        anchorQuote: "though only three years older",
        comment: "spoke this",
        clip: { audioRef: "blob://ev2", transcript: "the rival reappears", durationSeconds: 4 },
      },
      ctx,
    );
    const html = await renderNote(note);
    expect(html).toContain(`data-clip="blob://ev2"`); // the object-storage ref
    expect(html).toContain("the rival reappears"); // the transcript = the data
  });

  it("a clip with a FAILED/ABSENT transcript shows the honest marker, never a fabricated one", async () => {
    const ctx = ctxWith(CHUNKS);
    const note = await reResolveNote(
      {
        id: "n3",
        anchorQuote: "though only three years older",
        comment: "asr failed",
        clip: { audioRef: "blob://ev3", transcript: null }, // ASR failed/absent
      },
      ctx,
    );
    const html = await renderNote(note);
    expect(html).toContain(`data-clip="blob://ev3"`); // the clip still exists …
    expect(html).toContain("transcript unavailable"); // … with an HONEST marker
  });
});

// ── M4 — plain-text materiality: copy + re-resolve by quote ─────────────────

describe("plain-text materiality (M4)", () => {
  it("copying a note carries its quote-anchor (not a coordinate)", () => {
    const original: MarginNoteAuthored = {
      id: "n1",
      anchorQuote: "though only three years older",
      comment: "a thought",
      clip: { audioRef: "blob://ev1", transcript: "spoken" },
    };
    const copy = copyNote(original, "n2");
    expect(copy.id).toBe("n2"); // a fresh id
    expect(copy.anchorQuote).toBe(original.anchorQuote); // the QUOTE travels
    expect(copy.comment).toBe(original.comment);
    expect(copy.clip).toEqual(original.clip);
  });

  it("MOVING the underlying content re-resolves the anchor BY QUOTE, not a stale coordinate", async () => {
    // Before the edit: the quote sits at one offset in c2.
    const before = ctxWith(CHUNKS);
    const authored: MarginNoteAuthored = {
      id: "n1",
      anchorQuote: "though only three years older",
      comment: "follows the content",
    };
    const resolvedBefore = await reResolveNote(authored, before);
    expect(resolvedBefore.resolution.kind).toBe("match");
    const startBefore =
      resolvedBefore.resolution.kind === "match" ? resolvedBefore.resolution.candidate.start : -1;

    // The content is EDITED: text inserted BEFORE the quote shifts its offset.
    // (A stale coordinate would now point at the wrong text; the quote-anchor
    // re-resolves to the quote's NEW position — M4.)
    const moved: FixtureChunk[] = [
      CHUNKS[0],
      { ...CHUNKS[1], text: "An inserted preamble sentence. " + CHUNKS[1].text },
    ];
    const after = ctxWith(moved);
    const resolvedAfter = await reResolveNote(authored, after);
    expect(resolvedAfter.resolution.kind).toBe("match"); // still found by quote
    const startAfter =
      resolvedAfter.resolution.kind === "match" ? resolvedAfter.resolution.candidate.start : -1;

    // The offset MOVED with the content (re-resolved by quote), and still indexes
    // the correct text at the new position — not the stale coordinate.
    expect(startAfter).toBeGreaterThan(startBefore);
    expect(moved[1].text.slice(startAfter, startAfter + authored.anchorQuote.length)).toBe(
      "though only three years older",
    );
  });
});

// ── M6 — §9.0 in the composed view ──────────────────────────────────────────

describe("§9.0 in the composed marginalia view (M6)", () => {
  it("a withheld (non-servable) target anchors to the bounded chunk surface; the note's excerpt is null (no body leaked)", async () => {
    const withheld: FixtureChunk[] = [
      { chunk_id: "c9", text: "the withheld restricted body text", servable: false, servability: "restricted" },
    ];
    const ctx = ctxWith(withheld);
    // Anchor a note onto the known non-servable chunk (the per-chunk §9.0 path).
    const note = await reResolveNote(
      {
        id: "nw",
        anchorQuote: "the withheld restricted body",
        comment: "I noted this restricted source",
        targetChunkId: "c9" as ChunkId,
      },
      ctx,
    );
    expect(note.resolution.kind).toBe("withheld");

    const components: AnchoredWidgetComponents = {
      MarginNote: ({ comment, excerpt, servable }) =>
        createElement(
          "aside",
          { "data-servable": String(servable) },
          excerpt ? createElement("blockquote", null, excerpt) : null,
          createElement("p", null, comment),
        ),
    };
    const renderCtx: RenderContext = { pass: "main", layout: { resolve: () => null }, components };
    const plan = collectAnchoredWidgets([makeMarginaliaAugmentation([note])], ctx);
    const w = plan.all[0].widget;
    // Anchored to the bounded CHUNK surface, never a passage into the body.
    expect(w.anchor).toEqual({ kind: "chunk", chunkId: "c9" });

    const enacted = resolveAnchoredWidgets([w], renderCtx.layout);
    const html = enacted.map((e) => viewMarkup(e.widget.render(e.rect, renderCtx))).join("");
    expect(html).toContain("I noted this restricted source"); // the comment shows …
    expect(html).toContain(`data-servable="false"`); // … the §9.0 verdict carried …
    expect(html).not.toContain("withheld restricted body"); // … but NO body leaked
    expect(html).not.toContain("<blockquote"); // no excerpt block at all
  });
});
