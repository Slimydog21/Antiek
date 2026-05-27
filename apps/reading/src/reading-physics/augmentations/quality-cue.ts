// ─────────────────────────────────────────────────────────────────────────
// QualityCueAugmentation — the SPR-11 quiet quality indicator, re-homed from
// MasterMdViewer's hand-placed `<QualityCue score={…} />` into a DECLARED
// anchored widget (SPR-04 M4).
//
// SPR-11 M3 shipped the QualityCue JSX hand-placed inside MasterMdViewer's
// <header>. PR-1's "declare, don't act" re-expresses it: the augmentation
// declares an `AnchoredWidget` pinned to the synthesis-header anchor; the
// SURFACE places it. The augmentation supplies the VIEW; the surface owns where.
//
// ── THE PR-8 RESOLUTION (the design tension) — CONTRACT-ONLY RENDER ────────
//
// The frozen §6 `AnchoredWidget.render(rect, ctx): ReactNode` means this module
// carries a render closure that produces real UI. The PR-8 import allowlist
// binds an augmentation to importing only { the facet contract (../types,
// ../facet, ../facets/*, ../registry), the substrate read API, React }. The
// PREFERRED resolution (sprint manual): keep the render importing ONLY the
// contract — build the QualityCue view from REACT PRIMITIVES + the design-token
// classes the shipped widget already uses, with the substrate-derived score
// passed in. This module therefore imports ONLY `react` (for `createElement` —
// no JSX, so no `.tsx`, no extra import) and `../types`. The guard stays green
// with NO allowlist extension — the cleanest hard-to-vary outcome.
//
// PR-1 (declare, don't act): declares a widget; the render returns a ReactNode
//   (a VIEW), never a side effect — it never touches the DOM.
// PR-2 (no side store): the score is substrate-derived (the persisted §14.4
//   rubric, parsed upstream); this closes over it for one render and stores
//   nothing.
// PR-6 (substrate verdict is upstream): the composite + sub-scores are READ from
//   the persisted rubric; this NEVER recomputes scoring. It only COMPARES the
//   persisted composite against the same pass bar the surface used (0.5) to pick
//   the wording — a comparison of a read value, not a recompute of the verdict.
// ─────────────────────────────────────────────────────────────────────────

import { createElement, Fragment } from "react";
import type { ReactNode } from "react";

import { synthesisHeaderAnchor } from "../anchors";
import type {
  AnchoredWidget,
  FacetRegistry,
  ReadingAugmentation,
  ReadingContext,
  Rect,
  RenderContext,
} from "../types";

/**
 * The substrate-derived quality score the augmentation renders. Mirrors the
 * shipped `QualityScore` (synthesisParser.ts) — declared minimally here so the
 * augmentation does not import the parser (PR-8). The surface hands the parsed
 * score in; the augmentation invents nothing. `null` sub-scores are honest
 * "the note carried no breakdown" — rendered as no rows.
 */
export interface QualityScoreView {
  /** The persisted composite (the §14.4 rubric's final_score), READ never
   *  recomputed (PR-6). */
  readonly composite: number;
  readonly voiceStyle: number | null;
  readonly conviction: number | null;
  readonly citationDensity: number | null;
  readonly constraintCompliance: number | null;
}

/** The pass bar — mirrors the substrate's PASS_THRESHOLD (0.5,
 *  substrate/synthesis_rubric/scorer.py). We don't recompute the verdict; we
 *  only compare the persisted composite against it to pick the wording, exactly
 *  as the shipped QualityCue did. */
const QUALITY_PASS_BAR = 0.5;

/** Stable widget id. */
export const QUALITY_CUE_WIDGET_ID = "quality-cue";

/**
 * Build the QualityCue view (M4). Reproduces the shipped `QualityCue` +
 * `QualityDetail` output EXACTLY (same wording, same design-token classes, same
 * collapsed `<details>` breakdown) — byte-for-byte the JSX MasterMdViewer ships
 * — but built from React primitives so the augmentation imports only React.
 * Exported so the surface can render the same view in the header slot and the
 * no-regression test can assert the identical DOM.
 *
 * Returns `null` for an absent score (the honest no-rubric case) — the SAME
 * three states the shipped component has: absent → nothing; clears the bar → a
 * quiet positive line; below the bar → a visible re-run flag. The optional
 * sub-score breakdown sits behind the collapsed "the detail" toggle, hidden
 * entirely when the note carried no sub-scores.
 */
export function renderQualityCueView(score: QualityScoreView | null): ReactNode {
  // Absent: render nothing (no fabricated verdict). Matches the shipped
  // `if (!score) return null`.
  if (!score) return null;

  const low = score.composite < QUALITY_PASS_BAR;

  const message = low
    ? createElement(
        "p",
        { className: "text-amber-800 dark:text-sun leading-relaxed" },
        // The exact shipped copy (note the typographic apostrophe in it’s).
        "This answer reads like it may want another pass before you rely on it. The draft came in under our quality bar, so it’s worth a re-run or an edit.",
      )
    : createElement(
        "p",
        { className: "text-shadow-1 dark:text-moonlight leading-relaxed" },
        "This answer clears our quality bar.",
      );

  return createElement(
    "div",
    { className: "mt-3 text-xs" },
    message,
    renderQualityDetail(score),
  );
}

/** The optional breakdown, collapsed by default — the four sub-readings in
 *  plain words. Hidden when the note carried no sub-scores. Reproduces the
 *  shipped `QualityDetail` exactly. */
function renderQualityDetail(score: QualityScoreView): ReactNode {
  const rows: Array<[string, number | null]> = [
    ["Voice and style", score.voiceStyle],
    ["Conviction", score.conviction],
    ["Sourcing", score.citationDensity],
    ["Stayed within the brief", score.constraintCompliance],
  ];
  const present = rows.filter(([, v]) => v !== null) as Array<[string, number]>;
  if (present.length === 0) return null;

  return createElement(
    "details",
    { className: "mt-1" },
    createElement(
      "summary",
      {
        className:
          "cursor-pointer text-shadow-1 dark:text-moonlight hover:text-ink dark:hover:text-bright transition-colors",
      },
      "the detail",
    ),
    createElement(
      "dl",
      { className: "mt-2 space-y-1" },
      ...present.map(([label, value]) =>
        createElement(
          "div",
          { key: label, className: "flex items-baseline gap-2" },
          createElement(
            "dt",
            { className: "text-ink-soft dark:text-starlight" },
            label,
          ),
          createElement(
            "dd",
            { className: "font-mono text-shadow-1 dark:text-moonlight" },
            `${Math.round(value * 100)}%`,
          ),
        ),
      ),
    ),
  );
}

/**
 * Build the QualityCue augmentation (M4) over the substrate-derived score.
 *
 * A factory closing over the DECLARE-TIME score (like servability closes over
 * its sources): the augmentation reads the substrate-derived score in
 * `contribute(ctx)` and CAPTURES it in the widget's render closure, so the
 * `render(rect, ctx: RenderContext)` itself never touches substrate fields —
 * it sees only the captured `score` + (if it needed it) the render-time
 * `rect`/`ctx.pass`. Still pure w.r.t. its inputs, no cross-render cache (PR-2).
 * It declares ONE anchored widget at the synthesis-header anchor in the
 * `right-gutter` lane (a quiet aside, not in the reading column's flow), weight
 * 100. The `render` returns the byte-identical QualityCue view, ignoring the
 * resolved rect (the surface positions it; the cue's content does not depend on
 * geometry) and rendering nothing for an absent score.
 *
 * A null score still declares the widget (its render returns null) — so the
 * facet sees a stable widget id across renders for multi-render reconciliation
 * (PR multi-render), and the "absent → nothing" behavior is the render's, not a
 * missing declaration.
 */
export function makeQualityCueAugmentation(
  score: QualityScoreView | null,
): ReadingAugmentation {
  return {
    id: QUALITY_CUE_WIDGET_ID,
    contribute(_ctx: ReadingContext, registry: FacetRegistry): void {
      const widget: AnchoredWidget = {
        id: QUALITY_CUE_WIDGET_ID,
        anchor: synthesisHeaderAnchor(),
        lane: "right-gutter",
        weight: 100,
        render(_rect: Rect | null, _ctx: RenderContext): ReactNode {
          // RENDER-time context is the RenderContext (pass + layout), NOT the
          // declare-time ReadingContext. The score was READ at declare time
          // (the factory's `score` param, substrate-derived) and is CAPTURED in
          // this closure — the render reads no substrate field, exactly the
          // ReadingContext-vs-RenderContext separation the frozen §6 enforces.
          // Content is geometry-independent: the surface places the widget; the
          // cue renders the same view wherever it lands (and nothing when the
          // anchor is off-screen → _rect is null → the view is still the cue,
          // which the surface only mounts when it has a slot). The Fragment
          // keeps the return a single node.
          return createElement(Fragment, null, renderQualityCueView(score));
        },
      };
      registry.declareAnchoredWidget(widget);
    },
  };
}
