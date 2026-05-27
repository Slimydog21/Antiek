// ─────────────────────────────────────────────────────────────────────────
// ChaseLauncherAugmentation — the "Follow this" chase launcher, re-homed as a
// DECLARED anchored widget (SPR-04 M5).
//
// ChaseThread (modes/ResearchWorkstation/ChaseThread.tsx) launches a child
// research off a highlighted passage. Today the launcher is hand-mounted as an
// aside panel next to the reading column (modes/Reading/index.tsx). Under PR-1
// it stops being hand-positioned and instead declares an `AnchoredWidget`
// pinned to the PASSAGE it descends from; the surface places it. The launcher
// composes with QualityCue / AccrualView through the anchored-widgets facet —
// it imports none of them (PR-3).
//
// ── THE PR-8 RESOLUTION (the design tension) — SURFACE-OWNED COMPONENT MAP ──
//
// The ChaseThread launcher is GENUINELY heavy: it owns the ONE shipped launch
// path (startInvestigation + recordSpawnRelationship — PR-6 single-writer: the
// surface's existing write endpoint, NEVER a writer the augmentation opens), a
// LemonTextarea, VoiceChaseButton, AIActionFailure, a celebrate beat, and
// react-router navigation. A `render` that imported those directly would blow
// the PR-8 allowlist wide open (an augmentation may import only the facet
// contract + React). So this augmentation does NOT import ChaseThread. It uses
// the same PREFERRED resolution as the accrual augmentation: the SURFACE owns a
// `kind → component` map injected via `ctx.components` (an ADDITIVE widening of
// `RenderContext`), and the augmentation's render returns the surface-supplied
// `ChaseLauncher` component with the substrate-derived passage + parent ids.
// The augmentation declares the VIEW it wants (a chase launcher for THIS
// passage) WITHOUT importing it.
//
// This module therefore imports ONLY `react` (createElement) + `../types`. The
// guard stays green with NO allowlist extension. The surface owns BOTH the
// ChaseThread component and its behaviour (the single launch path, the
// reserved-id discipline, the §9.0-served-only seed) — the augmentation supplies
// only the captured passage text + parent/reserved ids (PR-2 / PR-6 — substrate
// data, never the wiring or the launch path).
//
// PR-1 (declare, don't act): declares a widget; never touches the DOM.
// PR-2 (no side store): the passage + ids are the only data; stored nowhere.
// PR-3 (named facets only): imports no sibling augmentation — composes with
//   QualityCue / accrual ONLY through the anchored-widgets facet.
// PR-4 (semantic anchor): pins to a `passage` anchor (chunk-relative offsets),
//   never a pixel — the launcher follows the passage under any transform.
// PR-6 (substrate upstream): the launch path is the surface's one shipped
//   write endpoint; this augmentation opens no writer of its own.
// ─────────────────────────────────────────────────────────────────────────

import { createElement } from "react";
import type { ReactNode } from "react";

import type {
  Anchor,
  AnchoredWidget,
  ChunkId,
  FacetRegistry,
  ReadingAugmentation,
  ReadingContext,
  Rect,
  RenderContext,
} from "../types";

/** Stable widget id. */
export const CHASE_LAUNCHER_WIDGET_ID = "chase-launcher";

/**
 * The substrate-derived seed for one chase launcher (SPR-04 M5). All fields are
 * read at DECLARE time and CAPTURED in the widget's render closure — the render
 * touches no substrate field (the ReadingContext-vs-RenderContext separation).
 */
export interface ChaseLaunchSpec {
  /** The chunk the chased passage lives in — the PR-4 semantic anchor base. */
  readonly chunkId: string;
  /** Char offsets INTO the chunk's text, half-open [start, end) — chunk-relative
   *  (PR-4), never a DOM offset, so the launcher follows under a transform. */
  readonly start: number;
  readonly end: number;
  /** The highlighted passage text that seeds the child research's question. */
  readonly passageText: string;
  /** The research the chase descends from (the new child's parent). */
  readonly parentInvestigationId: string;
  /** SPR-03's reserved escalation child id, when the passage maps to an
   *  escalated question. Present ⇒ launch INTO it (no orphan); absent ⇒ the
   *  substrate mints a fresh child. The launcher never renders it. */
  readonly reservedChildId?: string | null;
}

/**
 * Build a ChaseLauncher augmentation (M5) for one chased passage.
 *
 * Declares ONE anchored widget pinned to the PASSAGE anchor in the `inline-end`
 * lane (the launcher sits at the end of the passage's line, not in a gutter
 * aside — it descends from a specific run of text, so it follows that run).
 * weight 0 — a passage-level affordance, distinct lane from the header-anchored
 * QualityCue/accrual, so they never collide; when two launchers ever share an
 * anchor the id tie-break orders them deterministically.
 *
 * The `render` returns the surface-supplied `ChaseLauncher` component (from
 * `ctx.components`) with the captured passage + ids. When the surface did not
 * provide the component (any pass without it), the widget renders nothing — the
 * same graceful no-op as a null-resolving anchor. The augmentation never imports
 * ChaseThread; the surface owns the one launch path (PR-6).
 *
 * The widget id incorporates the chunk + offsets so two launchers on different
 * passages are distinct widgets (stable across renders for multi-render
 * reconciliation), while a single passage's launcher keeps one id.
 */
export function makeChaseLauncherAugmentation(
  spec: ChaseLaunchSpec,
): ReadingAugmentation {
  const widgetId = `${CHASE_LAUNCHER_WIDGET_ID}:${spec.chunkId}:${spec.start}:${spec.end}`;
  const anchor: Anchor = {
    kind: "passage",
    chunkId: spec.chunkId as ChunkId,
    start: spec.start,
    end: spec.end,
  };
  return {
    id: widgetId,
    contribute(_ctx: ReadingContext, registry: FacetRegistry): void {
      const widget: AnchoredWidget = {
        id: widgetId,
        anchor,
        lane: "inline-end",
        weight: 0,
        render(_rect: Rect | null, ctx: RenderContext): ReactNode {
          // RENDER-time context is the RenderContext (pass + layout +
          // surface-injected `components`), NOT the declare-time ReadingContext.
          // The passage + ids were captured at declare time (the factory's
          // `spec`, substrate-derived); the render reads no substrate field. The
          // SURFACE owns the ChaseThread component + its one launch path; the
          // augmentation only asks for it with the captured seed. Absent
          // component ⇒ nothing (graceful no-op).
          const Launcher = ctx.components?.ChaseLauncher;
          if (!Launcher) return null;
          return createElement(Launcher, {
            passageText: spec.passageText,
            parentInvestigationId: spec.parentInvestigationId,
            reservedChildId: spec.reservedChildId ?? null,
          });
        },
      };
      registry.declareAnchoredWidget(widget);
    },
  };
}
