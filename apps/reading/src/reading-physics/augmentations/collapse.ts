// ─────────────────────────────────────────────────────────────────────────
// The collapse affordance (SPR-05 M2) — cmd+scroll section collapse, the talk's
// signature spatial transform, with decorations compressed into a FINGERPRINT.
//
// ── WHAT THIS IS (and why it lives here but is SURFACE-DECLARED) ────────────
//
// Holding a modifier (⌘/Ctrl) and scrolling over a section COLLAPSES it: the
// section compresses spatially (LiquidText), and the decorations inside it do
// NOT vanish — they render as a compressed COLOR FINGERPRINT (the rhetorical /
// servability colors become a thin colored band). The talk's "fragment shader
// over a vertex shader": the collapse moves the geometry (vertex), the
// decorations follow and paint the squeezed colors (fragment).
//
// OQ2 RESOLUTION (canon §9 open question 2, owned by SPR-05): spatial transforms
// are SURFACE-DECLARED ONLY. So this module is NOT a `ReadingAugmentation` that
// pushes into `registry.declareSpatialTransform` — it is the surface's collapse
// CONTROLLER: it owns the ephemeral collapse view-state and PRODUCES (a) the
// `CollapseSpec[]` the surface folds into the layout-map's pipeline (via
// `buildCollapsePipeline`), and (b) the fingerprint plan that tells the surface
// which decorations to compress. The surface, not an augmentation, drives it.
// It lives under augmentations/ because the sprint manual fixes the path there
// AND because keeping it inside the CI-guarded boundary PROVES it never reaches
// past the facet contract (no DOM, no store, no sibling import) — the same bar
// every augmentation meets. It imports ONLY `../types` + `../facets/spatial-
// transform` (a facet barrel module, allowlisted) + React — guard stays green.
//
// ── PR-2 ESCAPE: collapse state is EPHEMERAL VIEW-STATE ────────────────────
//
// Which sections are collapsed is genuinely VIEW-STATE, not reading data — it is
// the ONE allowed PR-2 exception (canon §PR-2 bounded escape clause): view-only,
// reconstructible-from-nothing (a reload starts fully expanded — losing it loses
// no authored datum), and held in-memory for one session. It is NEVER persisted
// as reading data (no localStorage / event-log write). The `// PR-2 escape:`
// rationale comment sits on the state declaration below so the boundary lint's
// audit trail records it. (The guard's PR-2 patterns match persistence APIs; an
// in-memory immutable value trips none of them — but the comment is the
// documented, auditable marker the canon requires.)
//
// PR-1 (declare, don't act): produces VALUES (specs + a plan); touches no DOM.
// PR-4/PR-5: operates on `Anchor` + the layout-map's resolved `Rect` — semantic
//   identity + already-resolved geometry. It reads NO pixel itself (the surface
//   measured the base geometry once and feeds it to the layout-map; this asks the
//   layout-map where an anchor sits, exactly as a widget does).
// ─────────────────────────────────────────────────────────────────────────

import type { Anchor, LayoutMap, Rect } from "../types";
import {
  buildCollapsePipeline,
  collapseBandHeight,
  rectInCollapseBand,
} from "../facets/spatial-transform";
import type { CollapseRange, CollapseSpec } from "../facets/spatial-transform";

/** The compressed height (px) a collapsed section's fingerprint band occupies.
 *  Small but non-zero so the band — and the decoration colors squeezed into it —
 *  stay visible (the fingerprint, not a disappearance). A constant keeps the
 *  collapse deterministic; the surface may theme it. */
export const FINGERPRINT_BAND_HEIGHT_PX = 12;

/**
 * One collapsed section in the EPHEMERAL view-state (M2). It names the section
 * by its SEMANTIC bounds — the first and last anchor of the run the user folded —
 * plus the pre-transform pixel band the surface measured for it. The surface
 * mints one when the user ⌘+scrolls over a section; it lives only in memory.
 */
export interface CollapsedSection {
  /** Stable id for this collapsed section (pipeline tie-break + multi-render
   *  reconciliation). The surface derives it from the section's identity. */
  readonly id: string;
  /** The pre-transform vertical band the surface measured for the section. */
  readonly range: CollapseRange;
}

/**
 * The collapse VIEW-STATE — the ONE allowed PR-2 ephemeral exception.
 *
 * Immutable: `collapse`/`expand` return a NEW state (no mutation), so a render
 * reads a snapshot and there is no shared mutable store to leak (mirrors
 * `EnabledAugmentations`). Reconstructible from nothing: a reload starts empty
 * (everything expanded). Holds NO authored reading data — only which on-screen
 * sections the viewer chose to fold, this session.
 */
export class CollapseState {
  // PR-2 escape: ephemeral, view-only collapse state. Which sections the viewer
  // folded THIS SESSION is not reading data — it is reconstructible from nothing
  // (a reload starts fully expanded) and holds no authored datum. Never
  // persisted (no localStorage / no event-log write); an immutable in-memory map
  // rebuilt as the viewer folds/unfolds. This is the canon §PR-2 bounded escape.
  private readonly byId: ReadonlyMap<string, CollapsedSection>;

  constructor(sections: readonly CollapsedSection[] = []) {
    const m = new Map<string, CollapsedSection>();
    for (const s of sections) m.set(s.id, s);
    this.byId = m;
  }

  /** Return a new state with `section` collapsed (replaces a same-id section). */
  collapse(section: CollapsedSection): CollapseState {
    const next = new Map(this.byId);
    next.set(section.id, section);
    return new CollapseState([...next.values()]);
  }

  /** Return a new state with `id` expanded (no-op if absent). */
  expand(id: string): CollapseState {
    if (!this.byId.has(id)) return this;
    const next = new Map(this.byId);
    next.delete(id);
    return new CollapseState([...next.values()]);
  }

  /** Toggle a section collapsed/expanded (the ⌘+scroll gesture's effect). */
  toggle(section: CollapsedSection): CollapseState {
    return this.byId.has(section.id) ? this.expand(section.id) : this.collapse(section);
  }

  isCollapsed(id: string): boolean {
    return this.byId.has(id);
  }

  /** The collapsed sections, ordered by their band's TOP edge then id — so the
   *  pipeline `order` the surface assigns is top-to-bottom (a lower collapse sees
   *  the upward shift of an earlier one). A stable order keeps composition
   *  deterministic and the test meaningful. */
  list(): readonly CollapsedSection[] {
    return [...this.byId.values()].sort((a, b) =>
      a.range.topPx !== b.range.topPx
        ? a.range.topPx - b.range.topPx
        : a.id < b.id
          ? -1
          : a.id > b.id
            ? 1
            : 0,
    );
  }
}

/**
 * Turn the collapse view-state into the `CollapseSpec[]` the surface folds into
 * the layout-map's spatial-transform pipeline (M1/M2). `order` is the section's
 * top-to-bottom index (so an earlier/higher collapse runs first and a lower one
 * composes over its shift — two collapses compose deterministically). The
 * fingerprint band height is the compressed `targetHeight`.
 *
 * SURFACE-DECLARED (OQ2): the surface calls this and passes the result to
 * `buildCollapsePipeline` → `createLayoutMap(base, pipeline)`. No augmentation
 * does. Pure: `(state) → specs` — no state held, nothing persisted (PR-2).
 */
export function collapseSpecsFor(state: CollapseState): CollapseSpec[] {
  return state.list().map((section, index) => ({
    id: section.id,
    order: index, // top-to-bottom ascending; the layout-map sorts (order, id)
    range: section.range,
    mode: "collapse" as const,
    // A section shorter than the fingerprint band collapses to its own height
    // (clamped by makeCollapseTransform anyway) — never taller.
    targetHeight: Math.min(
      FINGERPRINT_BAND_HEIGHT_PX,
      collapseBandHeight(section.range),
    ),
  }));
}

/**
 * The surface's one-call helper: build the spatial-transform pipeline for the
 * current collapse state (M2). Equivalent to
 * `buildCollapsePipeline(collapseSpecsFor(state))`. The surface hands the result
 * to `createLayoutMap(base, pipeline)` so every anchor resolves POST-collapse —
 * and every widget/decoration follows for free (PR-5), having never learned the
 * geometry moved.
 */
export function collapsePipelineFor(state: CollapseState) {
  return buildCollapsePipeline(collapseSpecsFor(state));
}

/**
 * A decoration's place in the collapse rendering plan (M2). The surface paints a
 * decoration normally when `inFingerprint` is false; when true, the decoration's
 * anchor resolved INSIDE a collapsed band, so the surface paints it as part of
 * the compressed FINGERPRINT band (the squeezed color) rather than at full size.
 * The decoration is NEVER dropped — that is the talk's point (the colors compress
 * into a band, they do not disappear).
 *
 * `bandId` names which collapsed section's fingerprint it belongs to (so the
 * surface groups all fingerprint decorations of one band into one painted band).
 */
export interface FingerprintPlacement {
  /** The stable anchor key (the decoration's range identity). */
  readonly anchorKey: string;
  /** True ⇒ the anchor resolved inside a collapsed band → paint in the band. */
  readonly inFingerprint: boolean;
  /** The collapsed section the anchor fell into, when `inFingerprint`. */
  readonly bandId: string | null;
}

/**
 * Compute, for each decorated anchor, whether it sits inside a collapsed band —
 * the FINGERPRINT plan (M2). The surface resolves each decoration's anchor
 * through the POST-transform layout-map (so a folded anchor's compressed rect),
 * but to decide MEMBERSHIP we test the PRE-transform rect against the band (the
 * band is defined in pre-transform space). The surface therefore passes both:
 * the pre-transform resolver (a layout-map with NO pipeline, just base geometry)
 * and the collapse state.
 *
 * This reads geometry only via the layout-map's `resolve` — never a raw pixel
 * (PR-4): the SURFACE measured the base once; this asks "where did the anchor sit
 * pre-collapse?" exactly as a widget asks where its anchor sits. A null
 * resolution (anchor not laid out) ⇒ not in any fingerprint.
 *
 * @param decoratedAnchors  the anchors carrying a decoration this pass.
 * @param preTransformLayout a layout-map built from base geometry with an EMPTY
 *                           pipeline (pre-collapse positions).
 * @param state             the collapse view-state.
 */
export function fingerprintPlan(
  decoratedAnchors: readonly { readonly key: string; readonly anchor: Anchor }[],
  preTransformLayout: LayoutMap,
  state: CollapseState,
): FingerprintPlacement[] {
  const sections = state.list();
  return decoratedAnchors.map(({ key, anchor }) => {
    const rect: Rect | null = preTransformLayout.resolve(anchor);
    if (rect === null) {
      return { anchorKey: key, inFingerprint: false, bandId: null };
    }
    for (const section of sections) {
      if (rectInCollapseBand(rect, section.range)) {
        return { anchorKey: key, inFingerprint: true, bandId: section.id };
      }
    }
    return { anchorKey: key, inFingerprint: false, bandId: null };
  });
}
