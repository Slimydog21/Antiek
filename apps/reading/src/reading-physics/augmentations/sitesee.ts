// ─────────────────────────────────────────────────────────────────────────
// SiteSeeAugmentation — citation tints + a hover card (SPR-06 M2). The talk's
// "SiteSee" (Chang et al., re-grounded on Antiek): tint each citation marker by
// the reader's HISTORY with that source — green "already read", a "saved" tint,
// a "cited" tint — and surface the source's details in a hover card.
//
// SiteSee is the OTHER half of the SPR-06 composability proof. It declares tint
// decorations (on citation markers) + an anchored-widget hover card into the
// SPR-03/04 facets and NOTHING else. It does not know Skim (the rhetorical-role
// half) exists; the two meet only at the `decorations` facet (PR-3). Their
// composition is the deliverable — see skim-sitesee.compose.test.ts.
//
// ── WHERE THE READING HISTORY LIVES (M4) — the SUBSTRATE event log ─────────
//
// Diligence (api.ts): the substrate is a typed event log (TypedEventEnvelope /
// getTrajectory). A source's "cited" signal is already substrate-derived — a
// claim cites chunks (`supporting_chunk_ids` on a synthesize.delivered, and the
// `cited_chunk_ids` an authored section carries). A "saved" signal exists for
// promoted sources. A per-source "READ" signal (a reader opened this source)
// did NOT exist as a first-class event before this sprint. SiteSee does NOT
// invent a private store for it (PR-2 — that would break composition + trip the
// guard). Instead the SURFACE emits a `source.read` typed event through the ONE
// shipped write funnel (postTypedEvent → /events/typed → runtime/db_lock, the
// single-writer invariant — PR-6) when a reader opens a source, and resolves the
// per-source history back FROM the event log into the view below. The
// augmentation only READS the resolved state; it opens no writer of its own and
// emits no event itself. The event shape + the resolution are documented in
// reading-physics/README.md so SPR-08's agent knows the signal exists.
//
// ── §9.0 — the hover card shows ONLY bounded metadata for a withheld source ─
//
// The §9.0 servability gate is REUSED, not re-implemented (PR-6). The surface
// resolves each cited source's `servable` verdict + (only when servable) its
// `ip_holder_name` exactly as the shipped SourceCitation does. SiteSee passes
// the verdict THROUGH to the hover card and, for a NON-servable source, supplies
// ONLY the title — never the owner (the endpoint already withheld it with the
// body) and never any body text (the card's prop shape has no body field, so it
// is structurally impossible). The augmentation reads the verdict; it never
// overrides §9.0.
//
// ── THE PR-8 RESOLUTION — SURFACE-OWNED COMPONENT MAP (hover card) ─────────
//
// The hover card is real UI (a popover). A `render` that built it from Lemon/
// design-token components would risk the PR-8 allowlist. So SiteSee uses the
// SAME preferred resolution as accrual/chase-launcher: the SURFACE owns a
// `SiteSeeHoverCard` component injected via `ctx.components`, and the
// augmentation's render returns it with the substrate-derived, §9.0-gated props.
// This module therefore imports ONLY `react` (createElement) + `../types`.
//
// PR-1 (declare, don't act): declares decorations + a widget; never the DOM.
// PR-2 (no side store): the tint state + card metadata are substrate-derived,
//   handed in by the surface; stored nowhere; no persistence client imported.
// PR-3 (named facets only): imports the facet contract + React; no sibling
//   augmentation (not Skim, with which it composes).
// PR-4 (semantic anchor): tints + card anchor to the citation's CHUNK (and the
//   marker's claim), never a pixel.
// PR-6 (substrate upstream): history read from the event log; §9.0 verdict read,
//   never recomputed; the surface owns the one write path for `source.read`.
// PR-8 (agent-authorable): imports ONLY `react` + `../types`.
// ─────────────────────────────────────────────────────────────────────────

import { createElement } from "react";
import type { ReactNode } from "react";

import type {
  Anchor,
  AnchoredWidget,
  ChunkId,
  CitationHistoryState,
  ClaimId,
  Decoration,
  FacetRegistry,
  ReadingAugmentation,
  ReadingContext,
  Rect,
  RenderContext,
} from "../types";

// ── The closed tint vocabulary (the WHAT; §5.1) ────────────────────────────
//
// One class per history state — the WHAT the surface paints, NOT the painted
// CSS. The surface maps each state word to its concrete tint (cited / saved /
// read each get a treatment). "unseen" has NO class — it is the no-tint bucket
// (M5: a source with no history tints nothing). Mirrors the servability
// augmentation's closed-verdict-word vocabulary.

export const SITESEE_CITED_CLASS = "sitesee--cited";
export const SITESEE_SAVED_CLASS = "sitesee--saved";
export const SITESEE_READ_CLASS = "sitesee--read";

/** The history-state → closed-vocabulary tint className. `unseen` → null (no
 *  tint). Single source of truth so the surface and the augmentation agree. */
export function tintForState(state: CitationHistoryState): string | null {
  switch (state) {
    case "cited":
      return SITESEE_CITED_CLASS;
    case "saved":
      return SITESEE_SAVED_CLASS;
    case "read":
      return SITESEE_READ_CLASS;
    case "unseen":
      return null; // honest: no history ⇒ no tint (M5).
  }
}

/** The accessible tooltip per state (plain text; the surface paints it). */
export function tintTitleForState(state: CitationHistoryState): string | null {
  switch (state) {
    case "cited":
      return "You've cited this source";
    case "saved":
      return "You've saved this source";
    case "read":
      return "You've read this source";
    case "unseen":
      return null;
  }
}

/** Stable widget-id prefix for a source's hover card. */
export const SITESEE_HOVERCARD_ID = "sitesee-hovercard";

/**
 * The per-cited-source view SiteSee reads (M2/M4) — the adaptation boundary.
 * The SURFACE resolves it from substrate data the shipped citation rendering
 * already pulls (`getChunk` for the §9.0 verdict + title + owner) plus the
 * event-log history resolution (M4), and hands this minimal shape in. Every
 * field originates in the substrate (PR-2 / PR-6); the augmentation invents
 * nothing.
 *
 * `representativeChunkId` is the source's substrate-minted anchor (PR-4) — the
 * SAME handle the servability / ip-holder augmentations use. The hover card and
 * tint both anchor here, so the citation marker, its tint, and its card all
 * track one substrate identity under any transform.
 */
export interface SiteSeeSourceView {
  /** The source's representative chunk id (the anchor for tint + card). */
  readonly representativeChunkId: string;
  /** The claim the citation marker sits in — the marker tint also lands on this
   *  claim range, which is where it can OVERLAP a Skim role color (the M3
   *  composition's overlap case). Optional: a source not tied to a claim still
   *  tints its chunk. */
  readonly markerClaimId?: string | null;
  /** Reading-history state, RESOLVED from the substrate event log (M4). Defaults
   *  to "unseen" when the source has no history — tints nothing (M5). */
  readonly state: CitationHistoryState;
  /** §9.0 verdict, READ from the substrate (PR-6), never recomputed. Gates the
   *  hover card's bounded-vs-full metadata. */
  readonly servable: boolean;
  /** The source title — bounded metadata, always safe to show. Null when the
   *  substrate resolved no title. */
  readonly title: string | null;
  /** The IP-holder name — present only for a servable, owned source. The
   *  substrate returns null for an unknown owner OR a withheld (non-servable)
   *  source, so the augmentation never passes an owner for a withheld source. */
  readonly ipHolderName: string | null;
}

/**
 * Build the SiteSee augmentation (M2) over a set of resolved cited sources.
 *
 * A pure function from the (resolved) sources to declarations:
 *   - a TINT decoration per source whose history state is cited/saved/read,
 *     anchored to the source's chunk (and, when present, the marker's claim so
 *     it can overlap a Skim role color). An "unseen" source declares NO tint
 *     (M5: no history ⇒ nothing fabricated);
 *   - a hover-card anchored widget per source, in the `inline-end` lane (next
 *     to its citation marker), whose render returns the surface-supplied
 *     `SiteSeeHoverCard` with §9.0-gated bounded metadata.
 *
 * It returns nothing and mutates nothing (PR-1). It imports no sibling
 * augmentation — it composes with Skim ONLY at the `decorations` facet (PR-3).
 *
 * WHY a factory (matches servability/ip-holder/accrual): the sources are
 * render-scoped (resolved per synthesis, per render), so the augmentation closes
 * over the substrate-derived sources for THIS render — pure, no cross-render
 * cache (PR-2).
 */
export function makeSiteSeeAugmentation(
  sources: readonly SiteSeeSourceView[],
): ReadingAugmentation {
  return {
    id: "sitesee",
    contribute(_ctx: ReadingContext, registry: FacetRegistry): void {
      for (const source of sources) {
        const chunkAnchor: Anchor = {
          kind: "chunk",
          chunkId: source.representativeChunkId as ChunkId,
        };

        // ── 1. The tint decoration (M2) ───────────────────────────────────
        // The tint lands on the citation MARKER. When the marker is tied to a
        // claim, anchor the tint to the CLAIM so it can overlap a Skim role
        // color there (the composition overlap case); otherwise tint the chunk.
        const tintClass = tintForState(source.state);
        // "unseen" ⇒ tintClass null ⇒ declare NO tint (M5). No fabricated tint.
        if (tintClass !== null) {
          const tintTitle = tintTitleForState(source.state);
          const tintAnchor: Anchor = source.markerClaimId
            ? { kind: "claim", claimId: source.markerClaimId as ClaimId }
            : chunkAnchor;
          const tint: Decoration = {
            anchor: tintAnchor,
            className: tintClass,
            ...(tintTitle ? { title: tintTitle } : {}),
          };
          registry.declareDecoration(tint);
        }

        // ── 2. The hover card (M2) ────────────────────────────────────────
        // Always declared (even for an unseen source — its card still shows the
        // source's bounded details on hover; "unseen" just means no tint). The
        // card anchors to the source's CHUNK in the inline-end lane (next to the
        // marker). The render returns the surface-supplied card with §9.0-gated
        // props; an absent component ⇒ nothing (graceful no-op).
        //
        // §9.0: for a NON-servable source, pass ONLY the title + servable:false;
        // never the owner (the substrate already withheld it) and — structurally
        // — never any body (the card prop shape has no body field).
        const servable = source.servable;
        const ipHolderName = servable ? source.ipHolderName : null;
        const widgetId = `${SITESEE_HOVERCARD_ID}:${source.representativeChunkId}`;
        const widget: AnchoredWidget = {
          id: widgetId,
          anchor: chunkAnchor,
          lane: "inline-end",
          weight: 0,
          render(_rect: Rect | null, ctx: RenderContext): ReactNode {
            const Card = ctx.components?.SiteSeeHoverCard;
            if (!Card) return null;
            return createElement(Card, {
              title: source.title,
              servable,
              // Owner only when servable (else withheld — never leak it).
              ipHolderName,
              state: source.state,
            });
          },
        };
        registry.declareAnchoredWidget(widget);
      }
    },
  };
}
