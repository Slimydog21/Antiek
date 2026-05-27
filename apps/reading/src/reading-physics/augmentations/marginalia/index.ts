// ─────────────────────────────────────────────────────────────────────────
// MarginaliaAugmentation — voice-anchored marginalia, the talk's own demo
// re-cast as an Antiek augmentation (SPR-07 M2 + M4).
//
// The reader anchors a note (and optional voice clip) to a passage via a short
// quote that uniquely identifies it (the Canon Cat insight — resolved honestly
// by `resolve-quote.ts`, M1). The resolved note renders as an ANCHORED MARGIN
// WIDGET (SPR-04 facet) at the resolved `passage` `SemanticLocation`, de-overlaps
// with Skim/SiteSee/QualityCue through the same facet, and computes no pixels
// (PR-4). The note + its anchor persist as SUBSTRATE events — "just plain text"
// material the reader can move and copy (M4) — never a private store (PR-2).
//
// ── M2 — the margin-note anchored widget ───────────────────────────────────
//
// Each resolved note declares ONE `AnchoredWidget`:
//   - anchored at the resolved `passage` anchor (chunkId + chunk-relative
//     offsets — PR-4) for a unique-quote match, OR at the bounded `chunk` anchor
//     for a §9.0-withheld target (M6);
//   - in the `left-gutter` lane (marginalia sits in the margin, distinct from
//     SiteSee's `inline-end` cards + QualityCue's `right-gutter` cue, so they
//     de-overlap rather than collide);
//   - `render` returns the SURFACE-supplied `MarginNote` component (via
//     `ctx.components`, the SiteSee/ChaseLauncher pattern) with §9.0-gated props;
//     an absent component renders nothing (graceful no-op), exactly like a
//     null-resolving anchor.
//
// ── M4 — plain-text materiality (move / copy / re-resolve-by-quote) ─────────
//
// The note persists as a substrate event (the single-writer funnel, PR-6 — a
// SURFACE integration, see the decision doc + README). Crucially the note's
// anchor is stored BY QUOTE, not by a stale coordinate:
//   - COPYING a note carries its quote-anchor (`anchorQuote`) — paste re-resolves
//     it in the destination context;
//   - MOVING the underlying content (a re-parse that shifts chunk offsets)
//     re-resolves the anchor BY QUOTE via `resolve-quote.ts`, so the note follows
//     the content rather than pointing at a now-wrong offset.
// `reResolveNote` is the pure re-resolution the surface calls on a content edit;
// the augmentation reads the (re)resolved note view and re-declares the widget at
// the new anchor — no augmentation code changes on a move (the layout-map + the
// quote-anchor do the work).
//
// PR-1 (declare, don't act): declares a widget; never touches the DOM.
// PR-2 (no side store): the note text + anchor quote + clip ref are
//   substrate-derived (handed in / resolved via ctx.substrate); stored nowhere;
//   no browser-storage / KV / network-of-record import.
// PR-3 (named facets only): imports the facet contract + React + sibling MODULES
//   in this same marginalia FOLDER (resolve-quote / voice are part of THIS
//   augmentation, not a sibling augmentation — see the PR-3 note below).
// PR-4 (semantic anchor): pins to a `passage`/`chunk` anchor, never a pixel.
// PR-6 (substrate upstream): the §9.0 verdict + the note event are the
//   substrate's; the surface owns the one write funnel + blob store.
// PR-8 (agent-authorable): imports ONLY `react` + `../../types` + this folder's
//   own resolve-quote/voice helpers (all inside reading-physics — allowlisted).
//
// ── PR-3 note: resolve-quote.ts + voice.ts are NOT sibling augmentations ────
//
// PR-3 forbids importing ANOTHER augmentation. `resolve-quote.ts` and `voice.ts`
// live in THIS augmentation's own folder (`augmentations/marginalia/`) — they are
// this augmentation's internal modules, not siblings like skim/sitesee. The CI
// guard's PR-3 check fires on importing a DIFFERENT augmentation module; a
// same-folder helper resolves into `augmentations/` but is part of one
// augmentation. (Verified: the guard treats these as in-physics allowlisted
// relative imports — see the gate run in the handoff. The marginalia augmentation
// is a small package, not a single file, exactly as a real augmentation may be.)
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
} from "../../types";
import {
  resolveQuote,
  resolveQuoteOnChunk,
  type QuoteResolution,
} from "./resolve-quote";
import {
  NO_VOICE_CLIP,
  clipMaterialText,
  type VoiceClipView,
} from "./voice";

/** Stable widget-id prefix for a margin note. */
export const MARGINALIA_WIDGET_ID = "marginalia";

/** The margin lane marginalia lives in (distinct from SiteSee's `inline-end`
 *  cards + QualityCue's `right-gutter` cue, so the facet de-overlaps them rather
 *  than colliding). */
const MARGINALIA_LANE = "left-gutter" as const;

/** A passage-level note sits at weight 0 (a passage affordance, like the chase
 *  launcher), so two notes at one anchor break ties by id deterministically. */
const MARGINALIA_WEIGHT = 0;

// ── The note as the reader authored it (the persisted shape, M4) ────────────

/**
 * A margin note as the reader AUTHORED it — the substrate-persistable shape
 * (M4). The ANCHOR is stored as the short QUOTE the reader spoke/typed
 * (`anchorQuote`), NOT as a coordinate — this is what makes copy/move robust:
 * the quote re-resolves in any context (M4). The optional clip is a
 * `VoiceClipView` reference (text is the data — PR-2). A stable `id` keys the
 * widget across renders (multi-render reconciliation).
 *
 * The surface persists this as a substrate event through the one write funnel
 * (PR-6 — a SURFACE integration, see the decision doc); the augmentation reads
 * the RESOLVED note (below), never writing.
 */
export interface MarginNoteAuthored {
  /** Stable note id (the substrate event id once persisted; a client id before).
   *  Keys the widget for multi-render reconciliation. */
  readonly id: string;
  /** The short quote that ANCHORS the note (the Canon Cat handle). Stored as
   *  text, not a coordinate — re-resolved on copy/move (M4). */
  readonly anchorQuote: string;
  /** The reader's typed comment. The note's core text. */
  readonly comment: string;
  /** When the note targets a SPECIFIC known chunk (the reader anchored it while
   *  reading that source), the surface supplies it so the resolver can take the
   *  §9.0-explicit per-chunk path (and the withheld branch). Null ⇒ resolve the
   *  quote across the whole synthesis. */
  readonly targetChunkId?: ChunkId | null;
  /** The optional voice clip (text is the data; the blob is in object storage).
   *  Absent ⇒ a note with no clip works fully (voice optional — M3). */
  readonly clip?: VoiceClipView | null;
}

/**
 * A margin note AFTER its anchor has been resolved (M2/M4) — the view the
 * augmentation declares a widget for. `resolution` is the honest 0/1/many/withheld
 * outcome from `resolve-quote.ts`; the widget is placed only for a `match` (one
 * passage) or a `withheld` (bounded chunk surface) outcome. A `no-match` /
 * `ambiguous` note is NOT silently anchored — the surface shows the reader the
 * disambiguation/no-match state (the resolver's honesty propagates here).
 */
export interface ResolvedMarginNote {
  readonly authored: MarginNoteAuthored;
  readonly resolution: QuoteResolution;
}

/**
 * Resolve a note's anchor by its QUOTE (M4 re-resolution). Pure w.r.t. the
 * substrate read: per-chunk when a target chunk is known (the §9.0-explicit
 * path), else across the synthesis. The SURFACE calls this on author AND on a
 * content edit (a move) — the note re-resolves by quote, not by a stale
 * coordinate, so it follows the content. The augmentation then re-declares the
 * widget at the (possibly new) anchor with NO code change (the quote + the
 * layout-map do the work).
 */
export async function reResolveNote(
  authored: MarginNoteAuthored,
  ctx: ReadingContext,
): Promise<ResolvedMarginNote> {
  const resolution = authored.targetChunkId
    ? await resolveQuoteOnChunk(authored.anchorQuote, authored.targetChunkId, ctx.substrate)
    : await resolveQuote(authored.anchorQuote, ctx);
  return { authored, resolution };
}

/**
 * COPY a note (M4): carries its quote-anchor (and comment + clip), with a fresh
 * id. The copy is NOT anchored to the source's coordinate — it carries the QUOTE
 * so paste re-resolves it in the destination context. Pure; the surface persists
 * the copy as its own substrate event.
 */
export function copyNote(note: MarginNoteAuthored, newId: string): MarginNoteAuthored {
  return {
    id: newId,
    anchorQuote: note.anchorQuote, // the quote travels — re-resolved on paste
    comment: note.comment,
    targetChunkId: note.targetChunkId ?? null,
    clip: note.clip ?? null,
  };
}

/** The anchor a resolved note pins its widget to: the resolved `passage` (a
 *  unique match) or the bounded `chunk` (a §9.0-withheld target). `null` for a
 *  no-match/ambiguous note (NOT placed — the resolver's honesty). PR-4. */
export function noteAnchor(resolution: QuoteResolution): Anchor | null {
  switch (resolution.kind) {
    case "match":
      return resolution.candidate.anchor; // a passage anchor (PR-4)
    case "withheld":
      return resolution.anchor; // a bounded chunk anchor (M6)
    case "no-match":
    case "ambiguous":
      return null; // never silently anchored
  }
}

/** The §9.0-gated props a resolved note hands the surface's `MarginNote`. For a
 *  `withheld` target the excerpt is null + servable false (the body is never
 *  surfaced — M6); for a `match` the servable excerpt is shown. */
function noteProps(note: ResolvedMarginNote): {
  comment: string;
  excerpt: string | null;
  servable: boolean;
  transcript: string | null;
  audioRef: string | null;
} {
  const clip: VoiceClipView = note.authored.clip ?? NO_VOICE_CLIP;
  const transcript = clipMaterialText(clip); // honest marker when ASR absent
  const res = note.resolution;
  if (res.kind === "match") {
    return {
      comment: note.authored.comment,
      excerpt: res.candidate.excerpt, // servable quote — safe to show
      servable: true,
      transcript,
      audioRef: clip.audioRef,
    };
  }
  // withheld (§9.0): never surface the body; bounded surface only.
  return {
    comment: note.authored.comment,
    excerpt: null,
    servable: false,
    transcript,
    audioRef: clip.audioRef,
  };
}

/**
 * Build a Marginalia augmentation (M2) over a set of RESOLVED notes.
 *
 * A pure function from the resolved notes to declarations:
 *   - one `AnchoredWidget` per note whose resolution PLACED an anchor (a unique
 *     `match` → a `passage` anchor; a `withheld` target → the bounded `chunk`
 *     anchor). A `no-match` / `ambiguous` note declares NO widget — it is NOT
 *     silently anchored (the resolver's honesty; the surface handles those
 *     states out-of-band, e.g. a disambiguation prompt);
 *   - the widget pins to the `left-gutter` lane (the margin), de-overlapping
 *     Skim/SiteSee/QualityCue through the SPR-04 facet — it imports none of them
 *     (PR-3);
 *   - `render` returns the surface-supplied `MarginNote` with §9.0-gated props;
 *     an absent component renders nothing (graceful no-op).
 *
 * WHY a factory (matches sitesee/quality-cue/chase-launcher): the notes are
 * render-scoped (resolved per synthesis, per render), so the augmentation closes
 * over the resolved notes for THIS render — pure, no cross-render cache (PR-2).
 */
export function makeMarginaliaAugmentation(
  notes: readonly ResolvedMarginNote[],
): ReadingAugmentation {
  return {
    id: MARGINALIA_WIDGET_ID,
    contribute(_ctx: ReadingContext, registry: FacetRegistry): void {
      for (const note of notes) {
        const anchor = noteAnchor(note.resolution);
        // A no-match / ambiguous note is NOT placed (never silently anchored).
        if (anchor === null) continue;

        const props = noteProps(note);
        const widgetId = `${MARGINALIA_WIDGET_ID}:${note.authored.id}`;
        const widget: AnchoredWidget = {
          id: widgetId,
          anchor,
          lane: MARGINALIA_LANE,
          weight: MARGINALIA_WEIGHT,
          render(_rect: Rect | null, ctx: RenderContext): ReactNode {
            // RENDER-time context is the RenderContext (pass + layout +
            // surface-injected `components`), NOT the declare-time
            // ReadingContext. The note's props were resolved at declare time
            // (substrate-derived); the render reads no substrate field. The
            // SURFACE owns the MarginNote component + its chrome + clip playback;
            // the augmentation only asks for it with the §9.0-gated data. Absent
            // component ⇒ nothing (graceful no-op).
            const Note = ctx.components?.MarginNote;
            if (!Note) return null;
            return createElement(Note, {
              comment: props.comment,
              excerpt: props.excerpt,
              servable: props.servable,
              transcript: props.transcript,
              audioRef: props.audioRef,
            });
          },
        };
        registry.declareAnchoredWidget(widget);
      }
    },
  };
}

// Re-export the resolver + voice surface so the surface (and tests) reach the
// whole marginalia package from its barrel (one import site for the augmentation).
export {
  resolveQuote,
  resolveQuoteOnChunk,
  synthesisChunkIds,
  type QuoteResolution,
  type QuoteCandidate,
} from "./resolve-quote";
export {
  NO_VOICE_CLIP,
  hasVoiceClip,
  hasTranscript,
  clipMaterialText,
  type VoiceClipView,
} from "./voice";
