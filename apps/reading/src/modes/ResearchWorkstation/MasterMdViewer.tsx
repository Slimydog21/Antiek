import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { ArtifactExport } from "../../components/ArtifactExport";
import { toast } from "../../components/lemon/LemonToast";
import livingTvArt from "../../brand/werner/poses/session/werner_living_tv_session_v1.webp";
import { getChunk } from "../../lib/api";
import type { ChunkResponse } from "../../lib/api";
import { emitWernerExperience } from "../../werner/reactionBus";
import type {
  CompoundingStat,
  ParsedClaim,
  ParsedSynthesis,
  QualityScore,
  Recommendation,
  ReusedInsight,
} from "../../lib/synthesisParser";
import {
  RESTRICTED_TITLE,
  SERVABLE_CLASS,
  SERVABLE_TITLE,
  makeServabilityAugmentation,
} from "../../reading-physics/augmentations/servability";
import { makeIpHolderAugmentation } from "../../reading-physics/augmentations/ip-holder";
import {
  QUALITY_CUE_WIDGET_ID,
  makeQualityCueAugmentation,
} from "../../reading-physics/augmentations/quality-cue";
import {
  REVIEW_DUE_CLASS,
  makeReviewDueAugmentation,
} from "../../reading-physics/augmentations/review-due";
import type { ReviewDueClaimView } from "../../reading-physics/augmentations/review-due";
import type { ResolvedDecoration } from "../../reading-physics/facets/decorations";
import { anchorKey } from "../../reading-physics/facets/decorations";
import { renderEnacted, resolveAnchoredWidgets } from "../../reading-physics/facets/anchored-widgets";
import { EMPTY_LAYOUT_MAP } from "../../reading-physics/layout-map";
import {
  minimapLayoutFrom,
  projectDecorationsToMinimap,
  renderMinimap,
} from "../../reading-physics/minimap";
import { collectAnchoredWidgets, collectDecorations } from "../../reading-physics/registry";
import type { ClaimId, ChunkId, LayoutMap, ReadingContext, RenderContext } from "../../reading-physics/types";
import { openPdfPanel } from "../../workspace/actions";
import ChunkModal from "./ChunkModal";
import { buildLayoutMap } from "./readingGeometryPass";

/**
 * Renders a completed investigation's synthesis as a trustworthy
 * researcher's note: serif body, flowing prose, and — SPR-04 M1 — claim
 * support shown as NAMED SOURCES resolved through the provenance chain
 * (claim → chunk → document → title + locator), never the engine's
 * retrieval unit. A reader sees "from <em>Title</em>, p.12", not a
 * bracketed chunk count nor a raw chunk id.
 *
 * Source-opening honours the §9.0 retrieval gate: a named source opens
 * only when its source is servable (the `getChunk` endpoint carries the
 * verdict + withholds the body for a restricted source); a restricted /
 * taken-down source shows an honest "not available to open" state and is
 * never served.
 *
 * Falsification + execution risks are appendix material — collapsed by
 * default per the voice and style discipline (audit metadata, not
 * reading material).
 */
// ── SPR-08 M5 — the review-due augmentation, behind a default-OFF toggle ─────
//
// review-due (augmentations/review-due.ts) is the first AGENT-authored reading
// augmentation — a spaced-repetition "this claim is due to review" cue. It is a
// plain DECORATION (geometry-independent), so unlike SPR-05's collapse it needs
// no read-time geometry pass: it composes through the SAME decorations facet
// apply pass the §9.0 servability / IP-holder augmentations already run (the
// claim span gets the augmentation-declared `review-due` class).
//
// It ships behind this default-OFF toggle (anti-purgatory, PR-7): the feature is
// genuinely WIRED and runs through the real facet pass when flipped on, but the
// review-state it reads — which claims the reader is *due* to review — is a
// DEFERRED surface integration (resolving the reader's spaced-repetition schedule
// from the substrate), exactly like SPR-06's `source.read` signal. Until that
// resolver exists, the toggle passes an EMPTY `dueClaims`, so flipping it on
// shows the HONEST no-data state (nothing lights up) rather than fabricated
// review state. Filed: docs/decisions/spr-08-review-state-resolution-gap.md.
//
// DEFAULT-OFF byte-equivalence: with the toggle false, `composedReviewDueByClaim`
// runs no augmentation and returns an empty map, so every claim span renders with
// no extra class — byte-identical to the pre-SPR-08 render (the MasterMdViewer
// tests prove this unchanged: the default-off claim-span assertion + the SPR-02
// byte-equivalence test).
const REVIEW_DUE_ENABLED = false;

/**
 * DEFERRED: the surface resolves the reader's spaced-repetition schedule from
 * the substrate and returns the due claims here. Until that resolver ships, the
 * due set is EMPTY — review-due declares nothing (honest no-data), never a
 * fabricated due claim. See spr-08-review-state-resolution-gap.md.
 */
function resolveDueClaims(): readonly ReviewDueClaimView[] {
  return [];
}

/**
 * Run the decorations facet pass for the review-due augmentation over the
 * synthesis claims and the PASSED-IN due set, returning a lookup from a claim's
 * positional anchor key → its resolved review-due decoration (when the claim is
 * due). The surface's collect → combine half (§2) for the claim-decoration slot;
 * `ClaimBlock` owns the enact (it picks the class onto the claim span).
 *
 * The PURE seam: it takes the due set as an argument (it does not read the
 * toggle), so the augmentation→facet→map chain is drivable by a test with a
 * populated `dueClaims` — the toggle-ON liveness path (review-due.test against
 * `MasterMdViewer`). `composedReviewDueByClaim` is the toggle-gated wrapper.
 *
 * A PLAIN function, NOT a hook (mirrors `composedDecorationsByChunk` /
 * `renderHeaderQualityCue`): it calls no hooks, runs each render (cheap —
 * O(claims), pure), and the augmentation only DECLARES (PR-1).
 */
export function reviewDueDecorationsFor(
  synthesis: ParsedSynthesis,
  dueClaims: readonly ReviewDueClaimView[],
): Map<string, ResolvedDecoration> {
  const reviewDue = makeReviewDueAugmentation(dueClaims);
  const ctx: ReadingContext = {
    synthesis: {
      question: synthesis.question,
      // The augmentation anchors to claim positional ids (PR-4); it reads only
      // the due set passed in, so the claim list need only carry the ids the
      // surface knows about. (Empty due set ⇒ this is unused this sprint.)
      claims: synthesis.components.map((c) => ({
        claimId: String(c.index) as ClaimId,
        chunkIds: c.chunkIds as ChunkId[],
      })),
    },
    layout: { resolve: () => null },
    substrate: {
      getChunk: () =>
        // Not used by the decorations pass (the surface resolves the due set
        // upstream); present only to satisfy the frozen ReadingContext shape.
        Promise.reject(
          new Error("substrate.getChunk is not wired in the review-due pass"),
        ),
    },
  };
  const resolved = collectDecorations([reviewDue], ctx);
  const byKey = new Map<string, ResolvedDecoration>();
  for (const d of resolved) byKey.set(d.key, d);
  return byKey;
}

/**
 * The toggle-gated review-due decorations pass.
 *
 * GATED by `REVIEW_DUE_ENABLED`: off ⇒ the pass runs nothing and the returned
 * map is empty — every claim renders exactly as today (default-off
 * byte-equivalence). On ⇒ it runs the real pass (`reviewDueDecorationsFor`) over
 * the deferred-resolution due set (`resolveDueClaims()`, still empty), so it
 * declares nothing until review-state is wired (the honest dormant-correct
 * state, NOT fabricated).
 */
function composedReviewDueByClaim(
  synthesis: ParsedSynthesis,
): Map<string, ResolvedDecoration> {
  return REVIEW_DUE_ENABLED
    ? reviewDueDecorationsFor(synthesis, resolveDueClaims())
    : new Map();
}

// ── Living-Roadmap SPR-02 — the recompute debounce (M3) ──────────────────────
//
// WHAT TRIGGERS A RECOMPUTE, and what does NOT (the honest M3 model). The base
// geometry this surface measures is ROOT-RELATIVE (readingGeometryPass.ts
// normalises each rect by `box.top - rootBox.top`), so it is SCROLL-INVARIANT:
// scrolling the reading column moves the article and its claim spans by the SAME
// delta, leaving every root-relative rect unchanged. Scrolling therefore never
// changes the map — there is NO scroll listener here (a re-measure-on-scroll would
// be both misdirected and pure waste; see the geometry-pass comment below). The
// events that DO move geometry are LAYOUT-SIZE changes: a viewport resize, a web
// font finishing load, async content reflow (a streamed synthesis still settling).
// A `ResizeObserver` on the article fires on exactly those — uniformly, and untied
// to `window` (the article lives inside an inner overflow scroller, so a window
// listener would miss container-scoped reflow anyway).
//
// WHY 100ms FOR THE OBSERVER BURST (the no-magic-number rule — defensibility): a
// ResizeObserver does NOT fire per scroll frame, but it DOES fire a BURST during a
// continuous gesture — a drag-resize of the window, or a streaming synthesis whose
// DOM reflows on each appended chunk, each emit a rapid run of resize callbacks.
// Re-measuring + rebuilding the map on every one of those is the O(n) thrash the
// M3 milestone forbids. 100ms is ~6 frames at 60fps — below the ~100–200ms
// threshold at which a settle reads as "instant" to a human (so the minimap/gutter
// never feel laggy once the resize stops), yet coarse enough that a burst
// coalesces into ONE trailing-edge recompute instead of one per callback. A
// surface constant; tuning it never touches the physics.
const GEOMETRY_RECOMPUTE_DEBOUNCE_MS = 100;

export default function MasterMdViewer({
  synthesis,
}: {
  synthesis: ParsedSynthesis;
}) {
  const [openChunkId, setOpenChunkId] = useState<string | null>(null);

  // Living-TV: completed synthesis view is a deep_research_complete beat (once).
  useEffect(() => {
    emitWernerExperience("deep_research_complete");
  }, [synthesis.synthesisId]);

  // HPRJ SPR-05 M5 — the artifact-export affordance lives in the shared
  // <ArtifactExport> (the ONE neutral export affordance; the rights filter is
  // server-side and it surfaces the 403 reason). Rendered below when there's a
  // synthesis id.
  const synthesisId = synthesis.synthesisId;

  // SPR-08 M5 — the review-due decorations pass (default-off; empty map unless
  // the toggle is flipped AND review-state is wired). Computed once per render,
  // threaded into each ClaimBlock. Off ⇒ empty ⇒ byte-equivalent to today.
  const reviewDueByClaim = composedReviewDueByClaim(synthesis);

  // ── Living-Roadmap SPR-02 — the surface GEOMETRY PASS (M1/M3) ──────────────
  //
  // PR-4 BOUNDARY: the surface (NOT an augmentation) measures the DOM and builds
  // the live layout-map. All getBoundingClientRect calls live in
  // ./readingGeometryPass.ts — never under reading-physics/. A future maintainer
  // must NOT move measurement into an augmentation (see that module's header).
  //
  // The article column is the measurement root. The live map starts as
  // EMPTY_LAYOUT_MAP (the honest first-paint default: nothing measured yet ⇒ every
  // anchor resolves null ⇒ widgets render nothing) and is replaced by the measured
  // map in a useLayoutEffect that runs SYNCHRONOUSLY after the React commit, before
  // paint — so the resolved rects are read from the just-committed tree (the
  // reflow-during-measure mode is pinned to the commit boundary; a later DOM
  // mutation re-renders → the effect re-runs → fresh map).
  //
  // M3 RECOMPUTE DISCIPLINE — the honest model. The base geometry is ROOT-RELATIVE
  // (readingGeometryPass.ts normalises by `box.top - rootBox.top`) and therefore
  // SCROLL-INVARIANT: scrolling moves the article and its anchors by the same
  // delta, so the root-relative map is unchanged. Hence there is deliberately NO
  // scroll listener — re-measuring on scroll would be both MISDIRECTED (this
  // surface scrolls inside an inner `overflow-y-auto` ancestor in index.tsx, so a
  // `window` scroll listener never even fires on real reading scroll) AND
  // UNNECESSARY (the map cannot change). The only things that move geometry are
  // LAYOUT-SIZE changes — viewport resize, font load, async content reflow — so the
  // recompute trigger is a ResizeObserver on the article (it fires on exactly those,
  // uniformly, untied to `window`), debounced for the resize/reflow BURST case.
  //
  // We mount the UNSCOPED buildLayoutMap (NOT the viewport-scoped variant): on this
  // surface scoping would prune NOTHING — the transform pipeline is empty (SPR-05's
  // collapse is not bound this sprint) so there is no per-frame fold cost to cap,
  // and the base geometry is scroll-invariant so the visible band never narrows the
  // work. The scoped path (buildViewportScopedLayoutMap / buildViewportBand in
  // readingGeometryPass.ts) is RESERVED for when the reading column becomes its own
  // scroll container AND a non-empty transform pipeline makes per-frame fold cost
  // real — see that module's header for the reserved-seam contract.
  const articleRef = useRef<HTMLElement | null>(null);
  const [layoutMap, setLayoutMap] = useState<LayoutMap>(EMPTY_LAYOUT_MAP);

  useLayoutEffect(() => {
    const root = articleRef.current;
    if (!root) return;

    const recompute = () => {
      const node = articleRef.current;
      if (!node) return;
      // The transform pipeline is empty here; a live collapse passes
      // collapsePipelineFor(state) as the 2nd arg with no surface change (SPR-05's
      // seam is already threaded through buildLayoutMap).
      setLayoutMap(buildLayoutMap(node));
    };

    // Initial measure: synchronous, pre-paint (the M1 geometry pass). Correct as a
    // useLayoutEffect read — it avoids a first-paint flash of unmeasured widgets.
    recompute();

    // M3 — recompute on LAYOUT-SIZE change via a ResizeObserver on the article (NOT
    // a scroll listener: the map is scroll-invariant, see the block comment above).
    // The observer fires on viewport resize, font load, and async content reflow —
    // the events that actually move root-relative geometry. A single trailing-edge
    // timer coalesces a resize/reflow BURST into one rebuild after it settles. The
    // observer is disconnected in cleanup so it does not outlive the mount.
    let timer: ReturnType<typeof setTimeout> | null = null;
    const observer = new ResizeObserver(() => {
      if (timer !== null) clearTimeout(timer);
      timer = setTimeout(recompute, GEOMETRY_RECOMPUTE_DEBOUNCE_MS);
    });
    observer.observe(root);
    return () => {
      if (timer !== null) clearTimeout(timer);
      observer.disconnect();
    };
    // Re-run when the rendered synthesis changes (new claims ⇒ new anchors to
    // measure). The streamed-mutation case re-renders on its own and re-runs this.
  }, [synthesis]);

  return (
    <div className="bg-ice-0 dark:bg-charcoal-2">
      <article
        ref={articleRef}
        className="max-w-3xl mx-auto px-6 py-10 font-serif text-ink dark:text-bright">
        {/* Header band */}
        <header className="mb-8 pb-6 border-b border-rule dark:border-charcoal-1">
          {synthesis.question && (
            <h1 className="text-2xl leading-tight mb-3">
              {synthesis.question}
            </h1>
          )}
          {/* Living-TV invent strip — answer surface is product-mapped brand. */}
          <img
            src={livingTvArt}
            alt=""
            aria-hidden="true"
            data-testid="master-md-living-tv-art"
            className="mb-3 h-12 w-full max-w-md rounded-md object-cover object-center"
            loading="lazy"
            decoding="async"
          />
          {synthesisId && (
            <div className="mb-3">
              <ArtifactExport
                basePath={`/api/syntheses/${synthesisId}`}
                filenamePrefix={`synthesis-${synthesisId}`}
              />
            </div>
          )}
          <div className="flex items-center gap-3 text-xs font-mono text-shadow-1 dark:text-moonlight">
            <RecommendationBadge rec={synthesis.recommendation} />
            <span className="text-ink-mute dark:text-moonlight">·</span>
            <span>${synthesis.totalCostUsd.toFixed(4)} spent</span>
            {synthesis.domainsPatched.length > 0 && (
              <>
                <span className="text-ink-mute dark:text-moonlight">·</span>
                <span>
                  patched {synthesis.domainsPatched.length} domain skill
                  {synthesis.domainsPatched.length === 1 ? "" : "s"}
                </span>
              </>
            )}
            {/* SPR-06 M2 — the static "Save to notebook" affordance is REMOVED.
                The operator's directive ("these notebooks should just be
                automatically generated, not statically") supersedes manual
                save-from-research: the auto-notebook (modes/Notebook/AutoNotebook.tsx,
                /notebook/auto/:investigationId) is now the notebook surface,
                derived live from this research's graph rather than a snapshot
                saved from a button here. The manual TipTap Notebook editor stays
                reachable as its own surface (/notebook/:id) — only the
                save-FROM-research button is gone. No dead handler remains here.
                SCOPE (honest): this removes the SYNTHESIS-LEVEL save from
                MasterMdViewer. ClaimCard's claim-level "add to notebook"
                (components/ClaimCard.tsx) intentionally REMAINS — it is a ratified
                S7 affordance, and the auto-notebook is only PROPOSED, so retiring a
                ratified surface on the strength of an unratified concept would be
                over-reach. Whether M2 should also retire ClaimCard's save is an
                operator sign-off decision (flagged in the handoff), coupled to the
                auto-notebook ratification. NOTE: the auto-notebook is PROPOSED
                (sign-off pending) — see docs/decisions/spr-06-auto-notebook-proposed.md. */}
          </div>
          {/* SPR-11 M3 → SPR-04 M4 — the quiet quality cue, now a DECLARED
              anchored widget the surface PLACES via the anchored-widgets facet
              (PR-1: the cue declares; the surface enacts). Byte-equivalent to
              the prior inline `<QualityCue score={…} />` — same wording, classes,
              and collapsed detail — so this is a re-home, not a UX change. Still
              read from the persisted inline rubric, never recomputed (PR-6);
              renders nothing for an absent score.

              Living-Roadmap SPR-02 (M1): the cue is now placed against the LIVE
              layout-map (the measured map, EMPTY before first measure). QualityCue
              is geometry-INDEPENDENT (it pins to the header and renders without a
              rect), so this is byte-equivalent to the prior EMPTY_LAYOUT_MAP call
              — passing the live map proves the surface threads it everywhere, and
              lights up the moment a geometry-DEPENDENT widget is mounted here. */}
          {renderHeaderQualityCue(synthesis.qualityScore, layoutMap)}
        </header>

        {/* Thesis summary — flowing prose */}
        {synthesis.thesisSummary && (
          <section className="mb-8">
            <h2 className="text-sm font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-3">
              Thesis
            </h2>
            <p className="text-base leading-relaxed">
              {synthesis.thesisSummary}
            </p>
          </section>
        )}

        {/* Thesis components — each with hoverable citations */}
        {synthesis.components.length > 0 && (
          <section className="mb-8">
            <h2 className="text-sm font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-3">
              Components ({synthesis.components.length})
            </h2>
            <div className="space-y-6">
              {synthesis.components.map((c) => (
                <ClaimBlock
                  key={c.index}
                  claim={c}
                  onChunkClick={setOpenChunkId}
                  reviewDue={reviewDueByClaim.get(
                    anchorKey({ kind: "claim", claimId: String(c.index) as ClaimId }),
                  )}
                />
              ))}
            </div>
          </section>
        )}

        {/* Appendix — falsifications + risks + constraints, collapsed */}
        <Appendix synthesis={synthesis} />

        {/* SPR-10 M3/M4/M5 — the reuse-provenance footnote, a sibling of the
            Appendix in the SAME calm audit register (collapsed <details>, same
            classes). Present-only: renders NOTHING when this run reused nothing
            (empty reuseProvenance AND no compounding stat) — byte-identical to
            today's render, the qualityScore === null discipline. Never a hero
            banner, never a fabricated number. */}
        <ReuseProvenance
          insights={synthesis.reuseProvenance}
          stat={synthesis.compoundingStat}
        />
      </article>

      {/* ── Living-Roadmap SPR-02 (M2) — the minimap, a SECOND render pass of the
          SAME facets against the LIVE layout-map ──────────────────────────────
          PR-5 payoff: the minimap consumes the SAME ResolvedDecoration[] the main
          column resolves (here, the claim-anchored review-due decorations) and
          re-projects them through a minimap-scaled layout-map derived (by uniform
          vertical compression) from the live main-view map — NO re-measurement,
          NO re-combine. It lights up only when there are claim-anchored decorations
          AND the geometry pass has measured their anchors (default-off review-due
          ⇒ no marks ⇒ the minimap renders empty/aria-hidden, the honest no-data
          state). Wiring only: no minimap/augmentation logic changed. */}
      <ReadingMinimap byClaim={reviewDueByClaim} layoutMap={layoutMap} />

      <ChunkModal
        chunkId={openChunkId}
        onClose={() => setOpenChunkId(null)}
      />
    </div>
  );
}

// ── Living-Roadmap SPR-02 (M2) — the minimap mount ───────────────────────────
//
// A thin SURFACE component that runs the minimap's SECOND pass against the live
// layout-map. It is pure wiring: it imports the shipped minimap functions
// (minimapLayoutFrom / projectDecorationsToMinimap / renderMinimap) and feeds them
// the main view's resolved decorations + live map. No minimap LOGIC is touched
// (M2: "the diff under reading-physics/ is wiring only"). The minimap column is a
// narrow fingerprint of the document; a null-resolving anchor (off the minimap
// viewport, or not measured) paints nothing — exactly the contract the minimap
// already tolerates.

/** The minimap's uniform vertical compression factor (whole doc → a narrow
 *  column). 0.08 ≈ 1/12 — a long synthesis (~12 viewport-heights) squeezes into
 *  roughly one column. A surface constant; the minimap re-scales the live rects
 *  by it (minimap.tsx owns the math, this only supplies the factor). Exported so
 *  the minimap-projection test asserts against the value the surface ACTUALLY
 *  mounts (the mounted constant is the tested one — no drift). */
export const MINIMAP_SCALE = 0.08;
/** The minimap column width (px). Narrow by design — it shows COLOR, not text.
 *  Exported alongside MINIMAP_SCALE so the test pins the mounted value. */
export const MINIMAP_COLUMN_WIDTH_PX = 6;

function ReadingMinimap({
  byClaim,
  layoutMap,
}: {
  byClaim: Map<string, ResolvedDecoration>;
  layoutMap: LayoutMap;
}) {
  // The SAME resolved decorations the main column paints (shared, not re-derived).
  const resolved = Array.from(byClaim.values());
  // A second layout-map instance derived from the live main-view map by uniform
  // compression (minimap.tsx: it WRAPS the main map's resolve, so it inherits any
  // transform the main map folded — a collapsed section is collapsed here too).
  const minimapLayout = minimapLayoutFrom(layoutMap, MINIMAP_SCALE, MINIMAP_COLUMN_WIDTH_PX);
  const marks = projectDecorationsToMinimap(resolved, minimapLayout);
  return <>{renderMinimap(marks, MINIMAP_COLUMN_WIDTH_PX)}</>;
}

// ── Sub-components ───────────────────────────────────────────────────

export function ClaimBlock({
  claim,
  onChunkClick,
  reviewDue,
}: {
  claim: ParsedClaim;
  onChunkClick: (chunkId: string) => void;
  /** SPR-08 M5 — the COMBINED decoration the review-due augmentation declared for
   *  this claim's range (when the default-off toggle is on AND review-state is
   *  resolved). The augmentation declares the `review-due` verdict class; this
   *  component ENACTS it onto the claim span — never re-deciding "is this due"
   *  inline (PR-6: the augmentation read the verdict; the surface honors it).
   *  Undefined when the claim is not due (the common case, and ALWAYS the case
   *  while the toggle is off / review-state is deferred — empty `dueClaims` ⇒ no
   *  decoration ⇒ the claim span renders byte-identically to today). */
  reviewDue?: ResolvedDecoration | undefined;
}) {
  // ENACT the declared review-due verdict. Off / no-data ⇒ no class added ⇒
  // the span is byte-identical to the pre-SPR-08 render. The closed-vocabulary
  // class is appended only when the augmentation positively declared it.
  const claimClass = reviewDue?.classNames.includes(REVIEW_DUE_CLASS)
    ? REVIEW_DUE_CLASS
    : undefined;
  return (
    <div className="text-base leading-relaxed">
      <span className="font-mono text-xs text-ink-mute dark:text-moonlight mr-2">
        {claim.index}.
      </span>
      <span
        data-claim-id={String(claim.index)}
        {...(claimClass ? { className: claimClass } : {})}
        {...(reviewDue?.title ? { title: reviewDue.title } : {})}
      >
        {claim.claim}
      </span>
      {claim.rationale && (
        <p className="text-sm text-ink-soft dark:text-starlight mt-2 leading-relaxed pl-6 border-l-2 border-rule dark:border-charcoal-1 ml-1">
          {claim.rationale}
        </p>
      )}
      <div className="mt-2 flex items-center gap-2 flex-wrap pl-6">
        <ConfidenceChip
          confidence={claim.confidence}
          tier={claim.effectiveSourceTier}
        />
        <NamedSources chunkIds={claim.chunkIds} onPreview={onChunkClick} />
        {claim.supportingPathIndices.length > 0 && (
          <span className="text-[10px] font-mono text-shadow-1 dark:text-moonlight">
            + {claim.supportingPathIndices.length} cross-domain path
            {claim.supportingPathIndices.length === 1 ? "" : "s"}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Named sources (SPR-04 M1) ────────────────────────────────────────
//
// Resolve each cited chunk through the provenance chain (getChunk →
// document title + locator + §9.0 servability verdict), group the
// chunks by document, and render one NAMED source per document. This is
// the chunk-count → named-source translation: the engine's retrieval
// unit (the chunk) is collapsed into the human unit (the source), so a
// claim backed by three chunks of one paper reads as one named source,
// not a bracketed chunk count.

interface ResolvedSource {
  documentId: string;
  /** The source's title; null when the document carries no title. */
  title: string | null;
  /** A human locator (e.g. "p.12") derived from a chunk's section_path,
   *  or null when no chunk in the group encodes one. */
  locator: string | null;
  /** A representative chunk id for the inline preview + ⌘-open. */
  representativeChunkId: string;
  /** §9.0: whether clicking may open this source. False ⇒ honest
   *  "not available to open"; the body is already withheld by the API. */
  servable: boolean;
  /** SPR-10 M1 — "whose work grounds this": the source's IP-holder name
   *  (e.g. "MIT Press"), or null when the document has no resolved owner
   *  (honest "unknown owner", never invented). The §9.0 gate withholds the
   *  owner for a non-servable source, so this is null there too. */
  ipHolderName: string | null;
}

/** Derive a "p.NNN" locator from a section_path, when present. */
function locatorFromSectionPath(sectionPath: string | null): string | null {
  if (!sectionPath) return null;
  const m = sectionPath.match(/p\.?\s*(\d+)/i);
  return m ? `p.${m[1]}` : null;
}

/** Group resolved chunks by document into named sources, picking the
 *  first locator found per document. Order follows first appearance so
 *  the render is stable. */
function groupByDocument(chunks: ChunkResponse[]): ResolvedSource[] {
  const byDoc = new Map<string, ResolvedSource>();
  for (const c of chunks) {
    const existing = byDoc.get(c.document_id);
    const locator = locatorFromSectionPath(c.section_path);
    if (existing) {
      if (!existing.locator && locator) existing.locator = locator;
      continue;
    }
    byDoc.set(c.document_id, {
      documentId: c.document_id,
      title: c.document_title,
      locator,
      representativeChunkId: c.chunk_id,
      servable: c.servable,
      // §9.0: the endpoint already withholds the owner for a non-servable
      // source, so this is null there; we never invent it. (`?? null`
      // tolerates an older endpoint that omits the field entirely.)
      ipHolderName: c.ip_holder_name ?? null,
    });
  }
  return Array.from(byDoc.values());
}

function NamedSources({
  chunkIds,
  onPreview,
}: {
  chunkIds: string[];
  onPreview: (chunkId: string) => void;
}) {
  const [sources, setSources] = useState<ResolvedSource[] | null>(null);

  useEffect(() => {
    if (chunkIds.length === 0) {
      setSources([]);
      return;
    }
    let live = true;
    void (async () => {
      // Resolve each cited chunk through the provenance chain. A failed
      // fetch is dropped (honest: a source that can't be resolved is not
      // a source we'll name — rigor #1, never fabricate a title), so the
      // count of named sources can be fewer than the count of chunks.
      const settled = await Promise.allSettled(chunkIds.map((id) => getChunk(id)));
      if (!live) return;
      const ok = settled
        .filter((r): r is PromiseFulfilledResult<ChunkResponse> => r.status === "fulfilled")
        .map((r) => r.value);
      setSources(groupByDocument(ok));
    })();
    return () => {
      live = false;
    };
  }, [chunkIds]);

  if (chunkIds.length === 0) return null;
  if (sources === null) {
    return (
      <span className="text-[11px] text-shadow-1 dark:text-moonlight italic">
        resolving sources…
      </span>
    );
  }
  if (sources.length === 0) {
    // Resolved, but no source could be named (all fetches failed / no
    // titles). Honest, not a fabricated citation.
    return (
      <span className="text-[11px] text-shadow-1 dark:text-moonlight italic">
        source unavailable
      </span>
    );
  }

  // ── Facet apply pass (SPR-03: the first TWO-augmentation composition) ──
  //
  // Two augmentations now declare decorations on each source's range:
  //   - ServabilityAugmentation declares the §9.0 verdict class + tooltip;
  //   - IpHolderAugmentation declares the "whose work grounds this" owner name.
  // The decorations facet MERGES both contributions per source (§5.1), and the
  // surface here reads the combined verdict class AND owner name off ONE
  // resolved decoration. Neither augmentation imports the other — they meet
  // only at the named facet (PR-3). This is the physics' payoff on real shipped
  // code: composition for free, render byte-identical to the inline branch.
  // PR-1: the augmentations never touch the DOM; only this surface paints.
  const decorationByChunk = composedDecorationsByChunk(sources);

  return (
    <>
      {sources.map((s) => (
        <SourceCitation
          key={s.documentId}
          source={s}
          onPreview={onPreview}
          decoration={decorationByChunk.get(
            anchorKey({ kind: "chunk", chunkId: s.representativeChunkId as ChunkId }),
          )}
        />
      ))}
    </>
  );
}

/**
 * Run the decorations facet pass over the resolved sources, COMPOSING the
 * servability + IP-holder augmentations (SPR-03 M5), and return a lookup from a
 * source's anchor key → its combined decoration. This is the surface's
 * collect → combine half of the cycle (§2); SourceCitation owns enact. A plain
 * pure function — NOT a hook: NamedSources returns early above its call site,
 * so it cannot use hooks. The augmentations only declare, this never mutates
 * the DOM, and it runs each render (cheap — O(sources), pure).
 */
function composedDecorationsByChunk(
  sources: ResolvedSource[],
): Map<string, ResolvedDecoration> {
  // Both augmentations read substrate verdicts off each resolved source (PR-6:
  // read, never recompute) and declare a decoration per source on the SAME
  // anchor (the representative chunk). The facet merges them — servability's
  // verdict class with the IP-holder's owner name — so they compose without
  // importing each other (PR-3). The render context is minimal: decorations
  // need no layout-map (that resolves widget pixels, SPR-04), and the
  // augmentations pull no further substrate data, so `substrate` is a
  // shape-only stub never called this sprint.
  const servability = makeServabilityAugmentation(
    sources.map((s) => ({
      representativeChunkId: s.representativeChunkId,
      servable: s.servable,
    })),
  );
  const ipHolder = makeIpHolderAugmentation(
    sources.map((s) => ({
      representativeChunkId: s.representativeChunkId,
      ipHolderName: s.ipHolderName,
    })),
  );
  const ctx: ReadingContext = {
    synthesis: { question: null, claims: [] },
    layout: { resolve: () => null },
    substrate: {
      getChunk: () =>
        // Not used by the decorations pass (the surface resolves sources via
        // the shipped api.getChunk above); present only to satisfy the frozen
        // ReadingContext shape. SPR-04+ wires this to the real read API.
        Promise.reject(
          new Error("substrate.getChunk is not wired in the reading-physics slice"),
        ),
    },
  };
  // Collect both augmentations' declarations and combine. Order-independent:
  // passing [ipHolder, servability] yields the identical resolved set.
  const resolved = collectDecorations([servability, ipHolder], ctx);
  const byKey = new Map<string, ResolvedDecoration>();
  for (const d of resolved) byKey.set(d.key, d);
  return byKey;
}

function SourceCitation({
  source,
  onPreview,
  decoration,
}: {
  source: ResolvedSource;
  onPreview: (chunkId: string) => void;
  /** The COMBINED §9.0 decoration the ServabilityAugmentation declared for
   *  this source (SPR-02 facet apply pass). The augmentation declares the
   *  verdict (servable vs restricted) as a closed-vocabulary class; this
   *  component ENACTS it — choosing the DOM branch from the declared class,
   *  not by re-branching on `source.servable` inline. Undefined only if the
   *  pass produced no decoration for this source (defensive; treated as the
   *  restricted branch so an un-annotated source never silently opens). */
  decoration: ResolvedDecoration | undefined;
}) {
  const label = source.title ?? "an untitled source";
  const locator = source.locator ? `, ${source.locator}` : "";
  // SPR-10 M1 — "whose work grounds this": the IP-holder name is now declared
  // by the IpHolderAugmentation and merged into this combined decoration
  // (SPR-03 M5), no longer read inline off `source.ipHolderName`. The surface
  // owns the "published by …" phrasing (PR-6); the augmentation supplied only
  // the substrate-resolved name. Painted iff the combined decoration carries
  // exactly one owner (the single-source case). A null owner declared nothing,
  // so `ipHolderNames` is empty and no attribution is claimed — the honest
  // unknown. A non-servable source's owner was withheld by the endpoint
  // (ip_holder_name = null), so it never reaches the restricted branch below.
  const ownerName =
    decoration?.ipHolderNames.length === 1 ? decoration.ipHolderNames[0] : null;
  const owner = ownerName ? `, published by ${ownerName}` : "";

  // ENACT the declared §9.0 verdict (PR-6: the augmentation read `servable`
  // from the substrate; the surface honors it, never re-decides it). The
  // servable branch requires the explicitly-declared SERVABLE_CLASS; anything
  // else (RESTRICTED_CLASS, or a missing decoration) takes the withholding
  // branch — fail-closed so a source can never open without a positive
  // servable verdict.
  const servable = decoration?.classNames.includes(SERVABLE_CLASS) ?? false;

  if (!servable) {
    // §9.0: a restricted / taken-down source must NOT open. Show the
    // named source (so the reader knows what backs the claim) with an
    // honest "not available to open" state — never the content.
    return (
      <span
        className="text-[11px] text-ink-soft dark:text-starlight bg-ice-2 dark:bg-charcoal-1 px-1.5 py-0.5 rounded inline-flex items-center gap-1"
        title={decoration?.title ?? RESTRICTED_TITLE}
      >
        from {label}
        {locator}
        <span className="text-[10px] text-shadow-1 dark:text-moonlight">
          · not available to open
        </span>
      </span>
    );
  }

  return (
    <button
      onClick={(e) => {
        // ⌘/Ctrl-click opens the source jumped to its page; plain click
        // previews the chunk inline first (the modal path).
        if (e.metaKey || e.ctrlKey) {
          e.preventDefault();
          void (async () => {
            try {
              const chunk = await getChunk(source.representativeChunkId);
              if (!chunk.servable) {
                toast.err(`${label} isn’t available to open.`);
                return;
              }
              const page = source.locator
                ? parseInt(source.locator.replace(/\D/g, ""), 10)
                : undefined;
              openPdfPanel({
                documentId: chunk.document_id,
                page,
                title: `${label}${source.locator ? ` · ${source.locator}` : ""}`,
              });
            } catch (err) {
              toast.err(
                `Could not open ${label}: ${
                  err instanceof Error ? err.message : String(err)
                }`,
              );
            }
          })();
          return;
        }
        onPreview(source.representativeChunkId);
      }}
      className="text-[11px] text-ink-soft dark:text-starlight bg-ice-3 dark:bg-charcoal-1 hover:bg-ice-4 px-1.5 py-0.5 rounded transition-colors"
      title={decoration?.title ?? SERVABLE_TITLE}
    >
      from {label}
      {locator}
      {owner}
    </button>
  );
}

function ConfidenceChip({
  confidence,
  tier,
}: {
  confidence: ParsedClaim["confidence"];
  tier: number | null;
}) {
  const colorClass =
    confidence === "high"
      ? "bg-emerald-100 text-emerald-800"
      : confidence === "moderate"
        ? "bg-sun/20 text-amber-800"
        : confidence === "low"
          ? "bg-orange-100 text-orange-800"
          : "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight";
  return (
    <span
      className={`text-[10px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded ${colorClass}`}
    >
      {confidence}
      {tier !== null && ` · tier ${tier}`}
    </span>
  );
}

function RecommendationBadge({ rec }: { rec: Recommendation }) {
  const color =
    rec === "proceed"
      ? "bg-emerald-100 text-emerald-800"
      : rec === "pass"
        ? "bg-red-100 text-red-800"
        : rec === "conditional"
          ? "bg-sun/20 text-amber-800"
          : "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight";
  return (
    <span
      className={`text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded ${color}`}
    >
      {rec.replace(/_/g, " ")}
    </span>
  );
}

// ── Quality cue (SPR-11 M3 → re-homed SPR-04 M4) ─────────────────────────
//
// A quiet, plain-language read of the §14.4 inline rubric. The score is READ
// from the persisted rubric event by the parser; the augmentation only renders
// what it is handed and never re-implements scoring (PR-6). Three states are
// unchanged from the original inline component:
//   - absent  → render nothing (no fabricated score);
//   - clears the bar → a quiet positive cue;
//   - below the bar → a visible flag in plain words.
//
// SPR-04 M4 re-homes the cue from a hand-placed `<QualityCue score={…} />` into
// a DECLARED `AnchoredWidget` (augmentations/quality-cue.ts) the SURFACE places
// via the anchored-widgets facet (PR-1). The widget's view is BYTE-EQUIVALENT to
// the old inline JSX (same wording, classes, collapsed "the detail" toggle).
// `renderHeaderQualityCue` below is the surface's facet apply pass for the
// header slot.

/**
 * Run the anchored-widgets facet pass for the synthesis-header slot and return
 * the QualityCue widget's rendered node (SPR-04 M4). This is the surface's
 * collect → combine → enact cycle for one widget (§2), routed through the SAME
 * facet machinery the decorations pass uses.
 *
 * A PLAIN function, NOT a React hook — it is called from the viewer's JSX, but
 * the SPR-02 discipline holds regardless: a hook here would be fragile next to
 * the early-returning sub-components. It calls no hooks, runs each render
 * (cheap — O(1) widget, pure), and the augmentation only DECLARES (PR-1).
 *
 * The QualityCue widget's content is geometry-independent (the surface places
 * it in the header; the cue ignores the rect), so the layout-map can be the
 * empty map — the de-overlap enact resolves a null rect, the widget renders its
 * view all the same. The RenderContext is the minimal header pass: "main", the
 * (empty) layout-map, and no `components` (QualityCue needs no surface-injected
 * component — it builds its view from React primitives, PR-8 clean).
 */
function renderHeaderQualityCue(score: QualityScore | null, layout: LayoutMap) {
  // The score is substrate-derived (parsed from the persisted rubric); the
  // augmentation captures it at declare time and renders nothing for null
  // (the honest absent case). `QualityScore` structurally satisfies the
  // augmentation's minimal `QualityScoreView` (same five fields).
  const cue = makeQualityCueAugmentation(score);
  // Living-Roadmap SPR-02 (M1): the header pass now runs against the LIVE
  // layout-map the surface measured (was EMPTY_LAYOUT_MAP). QualityCue is
  // geometry-INDEPENDENT — it pins to the header and renders without a rect — so
  // the cue's view is byte-equivalent whether the map is empty or live (the
  // de-overlap enact resolves a null/real rect, the cue renders its view either
  // way). Threading the live map here proves the surface mounts it everywhere a
  // RenderContext is built; a future geometry-DEPENDENT header widget lights up
  // for free. Substrate is a shape-only stub never called here.
  const ctx: ReadingContext = {
    synthesis: { question: null, claims: [] },
    layout,
    substrate: {
      getChunk: () =>
        Promise.reject(
          new Error("substrate.getChunk is not wired in the header widget pass"),
        ),
    },
  };
  const enacted = resolveAnchoredWidgets(
    collectAnchoredWidgets([cue], ctx).all.map((p) => p.widget),
    layout,
  );
  const renderCtx: RenderContext = { pass: "main", layout };
  const headerWidget = enacted.find((e) => e.widget.id === QUALITY_CUE_WIDGET_ID);
  return headerWidget ? renderEnacted(headerWidget, renderCtx) : null;
}

function Appendix({ synthesis }: { synthesis: ParsedSynthesis }) {
  const hasContent =
    synthesis.falsificationConditions.length > 0 ||
    synthesis.executionRisks.length > 0 ||
    synthesis.hardConstraintsSatisfied !== null;
  if (!hasContent) return null;
  return (
    <details className="border-t border-rule dark:border-charcoal-1 pt-6 mt-8">
      <summary className="text-sm font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight cursor-pointer hover:text-ink dark:text-bright transition-colors">
        Appendix — falsification, risks, constraints
      </summary>
      <div className="mt-4 space-y-6 text-sm">
        {synthesis.falsificationConditions.length > 0 && (
          <section>
            <h3 className="text-xs font-mono uppercase text-ink-soft dark:text-starlight mb-2">
              Falsification conditions
            </h3>
            <ol className="list-decimal list-inside space-y-2 text-ink dark:text-bright">
              {synthesis.falsificationConditions.map((f, i) => (
                <li key={i}>
                  <span>{f.condition}</span>
                  {f.specificObservable && (
                    <div className="text-xs text-shadow-1 dark:text-moonlight mt-0.5 pl-6 italic">
                      Observable: {f.specificObservable}
                    </div>
                  )}
                </li>
              ))}
            </ol>
          </section>
        )}
        {synthesis.executionRisks.length > 0 && (
          <section>
            <h3 className="text-xs font-mono uppercase text-ink-soft dark:text-starlight mb-2">
              Execution risks
            </h3>
            <ul className="list-disc list-inside space-y-2 text-ink dark:text-bright">
              {synthesis.executionRisks.map((r, i) => (
                <li key={i}>
                  <span>{r.risk}</span>
                  {r.mitigation && (
                    <div className="text-xs text-shadow-1 dark:text-moonlight mt-0.5 pl-6 italic">
                      Mitigation: {r.mitigation}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}
        {synthesis.hardConstraintsSatisfied !== null && (
          <section>
            <h3 className="text-xs font-mono uppercase text-ink-soft dark:text-starlight mb-2">
              Constraint compliance
            </h3>
            <p className="text-ink dark:text-bright">
              Hard constraints:{" "}
              {synthesis.hardConstraintsSatisfied ? (
                <span className="text-emerald-700">satisfied</span>
              ) : (
                <span className="text-emperor">violated</span>
              )}
            </p>
          </section>
        )}
      </div>
    </details>
  );
}

// ── Reuse provenance (SPR-10 M3/M4/M5) ───────────────────────────────────────
//
// The flywheel's compounding made FELT — a quiet researcher's footnote, not a
// growth dashboard (§5). When a completed investigation reused prior knowledge,
// it surfaces (a) a one-line compounding stat and (b) the list of reused prior
// insights, each linking to the prior investigation it came from.
//
// PRESENT-ONLY (the cardinal discipline, mirrors `qualityScore === null`): when
// this run reused nothing — empty `insights` AND no `stat` — it renders NOTHING
// (returns null), byte-identical to the pre-SPR-10 render. There is NO zeroed
// "0 insights reused" placebo: the absent case is honest by saying nothing.
//
// HONESTY ON THE THREE NUMBERS (rigor #1): the stat renders only the fields it
// actually HAS. `reused` is real (the count of reused units). `avoided` /
// `fewerSources` require SPR-09's cold-baseline, which has NO per-investigation
// source today (no `compounding.measured` event) — so they are null and their
// clauses do not appear. The client NEVER computes a cold baseline (no
// source-count subtraction here — see docs/decisions/spr-10-flywheel-surface.md).
//
// REACHABILITY (M6): a reused insight links to `/inv/:sourceInvestigationId` —
// the EXISTING App.tsx route (line 107), no new route. The link is a plain
// semantic <a> (mirrors ChunkModal's OpenInDocumentButton), so navigating it
// honours §9.0: it opens the prior investigation's own synthesis surface, it
// does NOT fetch or display a withheld source body.

/** The plain-language compounding stat line, built ONLY from the fields the
 *  measurement actually carried. Declarative + sourced wording ("reused N
 *  insights …"), no promotional chrome. A clause appears only when its number
 *  is present (non-null) — so a stat with only `reused` reads "reused 2
 *  insights" with no fabricated avoided/fewer-than-cold tail. */
function compoundingStatLine(stat: CompoundingStat): string {
  const parts: string[] = [
    `reused ${stat.reused} insight${stat.reused === 1 ? "" : "s"}`,
  ];
  if (stat.avoided !== null) {
    parts.push(
      `avoided ${stat.avoided} re-derivation${stat.avoided === 1 ? "" : "s"}`,
    );
  }
  if (stat.fewerSources !== null) {
    parts.push(
      `${stat.fewerSources} fewer source${
        stat.fewerSources === 1 ? "" : "s"
      } than cold`,
    );
  }
  return parts.join(" · ");
}

function ReuseProvenance({
  insights,
  stat,
}: {
  insights: ReusedInsight[];
  stat: CompoundingStat | null;
}) {
  // A stat line shows ONLY when a per-run measurement carried a real number. A
  // {reused:0} measurement with no avoided/fewer is NOT a "0 insights reused"
  // placebo — it carries nothing worth a line. (compoundingStat is already gated
  // on the measurement event in the parser; this also guards the zeroed case.)
  const meaningfulStat =
    stat && (stat.reused > 0 || stat.avoided !== null || stat.fewerSources !== null)
      ? stat
      : null;
  // Present-only: nothing reused AND no meaningful stat ⇒ render nothing at all
  // (byte-identical to today; the qualityScore === null discipline).
  if (insights.length === 0 && !meaningfulStat) return null;

  return (
    <details
      className="border-t border-rule dark:border-charcoal-1 pt-6 mt-8"
      data-testid="reuse-provenance"
    >
      <summary className="text-sm font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight cursor-pointer hover:text-ink dark:text-bright transition-colors">
        Reuse provenance — what this built on
      </summary>
      <div className="mt-4 space-y-4 text-sm">
        {meaningfulStat && (
          <p className="text-shadow-1 dark:text-moonlight font-mono text-xs">
            {compoundingStatLine(meaningfulStat)}
          </p>
        )}
        {insights.length > 0 && (
          <section>
            <h3 className="text-xs font-mono uppercase text-ink-soft dark:text-starlight mb-2">
              Reused prior insights
            </h3>
            <ul className="list-disc list-inside space-y-2 text-ink dark:text-bright">
              {insights.map((ins, i) => (
                <li key={`${ins.unitId}-${i}`}>
                  <ReusedInsightLink insight={ins} />
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </details>
  );
}

/** One reused prior insight, rendered as the real identifier we have (the unit
 *  id — never a fabricated human title; the payload carries none). When the
 *  source investigation is known, the whole entry is a link to that prior
 *  investigation's EXISTING `/inv/:id` surface (M6 reachability); when it is
 *  not, it is plain text (honest "unknown origin", no dead link). */
function ReusedInsightLink({ insight }: { insight: ReusedInsight }) {
  const label = `prior insight ${insight.unitId}`;
  if (insight.sourceInvestigationId) {
    return (
      <a
        href={`/inv/${encodeURIComponent(insight.sourceInvestigationId)}`}
        className="text-ink-soft dark:text-starlight hover:text-ink dark:text-bright underline underline-offset-2 transition-colors"
      >
        {label}
      </a>
    );
  }
  return <span className="text-ink-soft dark:text-starlight">{label}</span>;
}

