// ─────────────────────────────────────────────────────────────────────────
// AccrualViewAugmentation — the §9 provenance-economics panel, re-homed as a
// DECLARED anchored widget (SPR-04 M5).
//
// AccrualView (modes/Economics/AccrualView.tsx) is the §9 accrual panel: whose
// work grounds a synthesis + what WOULD be owed, shown honestly and never paid.
// Under PR-1 it stops being hand-mounted and instead declares an `AnchoredWidget`
// pinned to the synthesis-header anchor (an aside lane); the surface places it.
//
// ── THE PR-8 RESOLUTION (the design tension) — SURFACE-OWNED COMPONENT MAP ──
//
// AccrualView is GENUINELY heavy: it owns its own §9 attribution/consent reads
// (getAttributionReport / getConsentView), a LemonButton, AIActionFailure, and a
// payout-refusal CALLBACK. A `render` that imported those directly would blow
// the PR-8 allowlist wide open (an augmentation may import only the facet
// contract + React). So this augmentation does NOT import AccrualView. It uses
// the PREFERRED resolution (sprint manual): the SURFACE owns a `kind → component`
// map, injected via `ctx.components` (an ADDITIVE widening of `RenderContext`),
// and the augmentation's render returns the surface-supplied `AccrualPanel`
// component with the substrate-derived synthesis id. The augmentation declares
// the VIEW it wants (AccrualPanel for this synthesis) WITHOUT importing it.
//
// This module therefore imports ONLY `react` (createElement) + `../types`. The
// guard stays green with NO allowlist extension. The surface owns BOTH the
// AccrualView component and its behaviour (the payout gate, the §9.0 honesty) —
// the augmentation supplies only the synthesis id (PR-2 / PR-6 — substrate
// data, never the wiring or the attribution math).
//
// PR-1 (declare, don't act): declares a widget; never touches the DOM.
// PR-2 (no side store): the synthesis id is the only datum; stored nowhere.
// PR-3 (named facets only): imports no sibling augmentation — composes with
//   QualityCue / chase-launcher ONLY through the anchored-widgets facet.
// PR-6 (substrate upstream): the panel reads §9 attribution from the substrate;
//   this augmentation re-implements no attribution math (the panel's honesty
//   logic is untouched — the physics governs PLACEMENT, not the panel's
//   substrate-honesty, exactly as the canon §3 map says).
// ─────────────────────────────────────────────────────────────────────────

import { createElement } from "react";
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

/** Stable widget id. */
export const ACCRUAL_WIDGET_ID = "accrual-view";

/**
 * Build the AccrualView augmentation (M5) for one synthesis.
 *
 * Declares ONE anchored widget at the synthesis-header anchor in the
 * `right-gutter` lane (an aside — the §9 panel is heavy analytics, the §11.2
 * "box as a facet" case the canon names), weight 50 (BELOW QualityCue's 100, so
 * when both land at the header anchor the de-overlap stacks QualityCue nearest
 * the anchor and the accrual panel below it — deterministic by weight).
 *
 * The `render` returns the surface-supplied `AccrualPanel` component (from
 * `ctx.components`) with this synthesis id. When the surface did not provide the
 * component (any pass without it), the widget renders nothing — the same graceful
 * no-op as a null-resolving anchor. The augmentation never imports AccrualView.
 */
export function makeAccrualAugmentation(synthesisId: string): ReadingAugmentation {
  return {
    id: ACCRUAL_WIDGET_ID,
    contribute(_ctx: ReadingContext, registry: FacetRegistry): void {
      const widget: AnchoredWidget = {
        id: ACCRUAL_WIDGET_ID,
        // The SAME synthesis-header anchor QualityCue uses (shared via the
        // non-augmentation `../anchors` helper — never importing QualityCue,
        // PR-3). Two widgets at one anchor is exactly the §5.2 de-overlap case.
        anchor: synthesisHeaderAnchor(),
        lane: "right-gutter",
        weight: 50,
        render(_rect: Rect | null, ctx: RenderContext): ReactNode {
          // RENDER-time context is the RenderContext (pass + layout +
          // surface-injected `components`), NOT the declare-time ReadingContext.
          // The synthesis id was captured at declare time (the factory param,
          // substrate-derived); the render reads no substrate field. The SURFACE
          // owns the AccrualView component + its behaviour; the augmentation only
          // asks for it with the captured id. Absent component ⇒ nothing
          // (graceful no-op; the surface may not provide it in a minimap pass).
          const Panel = ctx.components?.AccrualPanel;
          if (!Panel) return null;
          return createElement(Panel, { synthesisId });
        },
      };
      registry.declareAnchoredWidget(widget);
    },
  };
}
