// SPR-07 M2 + M6 — Gutter pill rendering + behavior-event funnel.
//
// The Gutter component is the in-page-margin surface that replaces
// CrossDocSidebar as the primary cross-doc affordance (see
// SPR-07 spec §Goal). It is rendered absolutely-positioned alongside
// the PDF page; each active highlight gets a pill-stack at its
// vertical position.
//
// Responsibilities:
//   1. Render 1–3 GutterPill components per highlight.
//   2. Emit the cross_doc_link_* funnel events:
//        - cross_doc_link_surfaced once per highlight (M6 spec note)
//        - cross_doc_link_clicked on Open
//        - cross_doc_link_dismissed on highlight clear without click
//   3. Wire pill hover → preview popover (CitePreview).
//
// The spec page mentions a fourth "previewed" event on hover. As of
// taxonomy v2 (2026-05-22) `cross_doc_link_previewed` IS in the
// closed taxonomy at substrate/behavior/taxonomy.py:BehaviorEventType.
// We emit:
//   - surfaced  once per highlight (system-initiated, fires when the
//                fetcher returns ≥1 link)
//   - previewed once per hover-enter on any pill (per-pill granular)
//   - clicked   when the operator hits Open
//   - dismissed when the highlight is cleared without any click
// The funnel is surfaced → previewed → clicked / dismissed, matching
// the SPR-07 M6 acceptance scenario.
//
// Why pill-count is 3 (rigor #5 — defensibility):
//   The brainstorm identified eyeball-distance as the cross-doc UX
//   problem. Pills in the gutter solve it BY being tiny and close to
//   the highlighted line. Showing 5 pills would push past the visual
//   budget the gutter provides (one pill is ~24px tall; 5 stacked is
//   120px, which collides with adjacent paragraphs at default
//   PDF zoom). 3 keeps the cluster under 80px and reads as "here are
//   a few related passages", not "here is a list to consume". The
//   dismiss-event metric is what would justify changing 3 → 2 or 3 → 5:
//   if the operator dismisses 90% of pills consistently, we are
//   showing too many; if they click 1 of 3 every time the count is
//   calibrated. See SCORING.md "What would change these weights" for
//   the funnel-driven tuning path.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchCrossDocLinks } from "../../../../api/cross_doc/links";
import type { CrossDocLink } from "../../../../api/cross_doc/links";
import {
  BehaviorEventType,
  emitBehaviorEvent,
} from "../../../lib/behaviorEvents";
import { useUserSettings } from "../../../settings/crossDocSettings";

import CitePreview from "../CitePreview";
import GutterPill from "./GutterPill";

/** Pill-count limit. Chosen number — see header comment for the
 *  rationale (eyeball distance, visual budget, attention). */
export const PILL_COUNT_LIMIT = 3;

/** Time-to-pill budget (ms). M2 acceptance: pills appear within 300ms
 *  of highlight finalize. The Python query bench measures ~10ms P99
 *  on 10k chunks; the budget here is the UI-side total (fetch +
 *  layout). */
export const PILL_RENDER_BUDGET_MS = 300;

/** Public input — one highlight that earned a pill stack. The
 *  consumer (PdfViewer) creates these on selection finalize and
 *  removes them on selection clear. */
export interface ActiveHighlight {
  /** Stable id — at minimum unique within the lifetime of one
   *  document session. */
  highlightId: string;
  documentId: string;
  page: number;
  bbox: [number, number, number, number];
  /** Absolute vertical position of the highlight relative to the
   *  Gutter's containing element. Set by the caller after
   *  measuring the selection rect. */
  topPx: number;
  /** The selected text — used as the query for the cross-doc
   *  substrate call. */
  selectedText: string;
}

/** Props. The Gutter is a "render along the right edge" component;
 *  the parent PdfViewer owns the highlight lifecycle. */
export interface GutterProps {
  /** All currently-active highlights. The component renders one
   *  pill-stack per item. */
  highlights: ActiveHighlight[];
  /** Optional injection for tests (Vitest). When unset, falls back
   *  to the real fetchCrossDocLinks from
   *  apps/reading/api/cross_doc/links.ts. */
  fetchLinks?: typeof fetchCrossDocLinks;
}

/** Internal state per highlight — links + funnel bookkeeping. */
interface HighlightState {
  links: CrossDocLink[];
  surfacedAt: number;
  loading: boolean;
  // Funnel state — whether we have already emitted the resolution
  // event for this highlight. The dismissal fires when the
  // highlight goes away WITHOUT a click; this flag suppresses the
  // dismissal when the operator clicked through.
  clicked: boolean;
  dismissed: boolean;
}

export default function Gutter({ highlights, fetchLinks }: GutterProps) {
  const fetcher = fetchLinks ?? fetchCrossDocLinks;
  const includePublic = useUserSettings(
    (s) => s.includePublicGraphInCrossDoc,
  );

  // Per-highlight state, keyed by highlightId. We keep this in a ref
  // for the dismissal effect (which runs when the highlight is
  // removed) — otherwise the previously-loaded links are gone by the
  // time we want to emit.
  const stateRef = useRef(new Map<string, HighlightState>());
  // Force render on state change. The ref carries the live data;
  // version is for re-render only.
  const [version, setVersion] = useState(0);
  const bump = useCallback(() => setVersion((v) => v + 1), []);

  // Track which highlight is hovered → renders the CitePreview.
  const [hovered, setHovered] = useState<{
    highlightId: string;
    linkIndex: number;
  } | null>(null);

  // Fetch links for any highlight we haven't seen yet. Emit
  // cross_doc_link_surfaced on the first non-empty result.
  useEffect(() => {
    let cancelled = false;
    for (const h of highlights) {
      if (stateRef.current.has(h.highlightId)) continue;
      stateRef.current.set(h.highlightId, {
        links: [],
        surfacedAt: Date.now(),
        loading: true,
        clicked: false,
        dismissed: false,
      });
      bump();
      // Kick off the fetch.
      void (async () => {
        const links = await fetcher(
          {
            document_id: h.documentId,
            page: h.page,
            bbox: h.bbox,
            selected_text: h.selectedText,
          },
          {
            topK: PILL_COUNT_LIMIT,
            includePublicGraph: includePublic,
          },
        );
        if (cancelled) return;
        const slot = stateRef.current.get(h.highlightId);
        if (!slot) return;
        slot.links = links.slice(0, PILL_COUNT_LIMIT);
        slot.loading = false;
        slot.surfacedAt = Date.now();
        bump();
        // M6 acceptance: surfaced fires ONCE per highlight (not per
        // pill) even when 3 pills are returned. Don't emit when
        // there are zero links — surfacing nothing is not a
        // surface event.
        if (slot.links.length > 0) {
          const first = slot.links[0];
          emitBehaviorEvent({
            eventType: BehaviorEventType.CROSS_DOC_LINK_SURFACED,
            state: {
              document_id: h.documentId,
              reading_mode: "wrestle",
              trigger_chunk_id: null,
            },
            action: {
              link_id: h.highlightId,
              target_document_id: first.document_id,
              target_chunk_id: first.chunk_id,
              surface_confidence: first.score,
            },
            documentId: h.documentId,
          });
        }
      })();
    }
    return () => {
      cancelled = true;
    };
  }, [highlights, fetcher, includePublic, bump]);

  // Detect removed highlights → emit dismissed (unless clicked).
  const prevIdsRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    const currentIds = new Set(highlights.map((h) => h.highlightId));
    const prevIds = prevIdsRef.current;
    for (const oldId of prevIds) {
      if (currentIds.has(oldId)) continue;
      const slot = stateRef.current.get(oldId);
      if (!slot) continue;
      if (!slot.clicked && !slot.dismissed && slot.links.length > 0) {
        const elapsedSec = (Date.now() - slot.surfacedAt) / 1000;
        emitBehaviorEvent({
          eventType: BehaviorEventType.CROSS_DOC_LINK_DISMISSED,
          state: {
            document_id: slot.links[0].document_id,
            link_id: oldId,
            reading_mode: "wrestle",
            elapsed_since_surfaced_s: elapsedSec,
          },
          action: { reason: "highlight_cleared" },
        });
        slot.dismissed = true;
      }
      // Garbage-collect the entry so re-entering the same highlight
      // id (rare but possible) treats it as a fresh surface.
      stateRef.current.delete(oldId);
    }
    prevIdsRef.current = currentIds;
  }, [highlights]);

  const onOpen = useCallback(
    (highlightId: string, link: CrossDocLink) => {
      const slot = stateRef.current.get(highlightId);
      if (slot) slot.clicked = true;
      const elapsedSec = slot
        ? (Date.now() - slot.surfacedAt) / 1000
        : null;
      // Source document for the cite_jump emit. The Gutter is keyed on
      // a per-highlight basis; every highlight references the document
      // it was created on, so we can pull source_document_id off the
      // active highlight rather than threading a prop.
      const sourceDocId =
        highlights.find((h) => h.highlightId === highlightId)?.documentId ?? null;

      emitBehaviorEvent({
        eventType: BehaviorEventType.CROSS_DOC_LINK_CLICKED,
        state: {
          document_id: link.document_id,
          link_id: highlightId,
          reading_mode: "wrestle",
          elapsed_since_surfaced_s: elapsedSec,
        },
        action: {
          target_document_id: link.document_id,
          target_chunk_id: link.chunk_id,
        },
      });

      // cite_jump — taxonomy v2 emit. The Gutter is one of the natural
      // call sites with full source/target document context, so the
      // schema's required (document_id, target_document_id, direction)
      // fields are all available here. Swallow on failure per SPR-01
      // rigor.
      if (sourceDocId) {
        try {
          emitBehaviorEvent({
            eventType: BehaviorEventType.CITE_JUMP,
            state: {
              document_id: sourceDocId,
              reading_mode: "wrestle",
            },
            action: {
              target_document_id: link.document_id,
              target_chunk_id: link.chunk_id,
              direction: "forward",
            },
          });
        } catch {
          // non-fatal
        }
      }

      // Cite-jump navigation: route through the existing /wrestle/<id>?page=
      // pattern, extended with ?chunk= per M4. The receiving WrestleApp
      // reads both params on mount.
      const params = new URLSearchParams({
        page: String(link.page),
        chunk: link.chunk_id,
      });
      window.location.href = `/wrestle/${link.document_id}?${params.toString()}`;
    },
    [highlights],
  );

  // useMemo-able snapshot for render — derived from highlights +
  // version so the JSX reads correctly when the ref mutates.
  const render = useMemo(() => {
    void version; // referenced for the re-render dep
    return highlights.map((h) => ({
      h,
      slot: stateRef.current.get(h.highlightId),
    }));
  }, [highlights, version]);

  return (
    <div
      data-testid="gutter"
      className="pointer-events-none absolute inset-y-0 right-0 w-[60px] z-10"
    >
      {render.map(({ h, slot }) => {
        if (!slot || slot.links.length === 0) return null;
        return (
          <div
            key={h.highlightId}
            data-testid={`gutter-stack-${h.highlightId}`}
            className="pointer-events-auto absolute right-1 flex flex-col gap-1"
            style={{ top: `${h.topPx}px` }}
          >
            {slot.links.map((link, idx) => (
              <GutterPill
                key={`${link.chunk_id}-${idx}`}
                link={link}
                onOpen={() => onOpen(h.highlightId, link)}
                onHoverChange={(isHovered) => {
                  setHovered(
                    isHovered
                      ? { highlightId: h.highlightId, linkIndex: idx }
                      : null,
                  );
                  // Taxonomy v2 (2026-05-22): cross_doc_link_previewed
                  // is now in the closed taxonomy. Emit once per
                  // hover-enter (not hover-exit) so the funnel sees
                  // surfaced → previewed → clicked / dismissed. Emit
                  // failure is non-fatal.
                  if (isHovered) {
                    try {
                      emitBehaviorEvent({
                        eventType: BehaviorEventType.CROSS_DOC_LINK_PREVIEWED,
                        state: {
                          document_id: h.documentId,
                          reading_mode: null,
                          trigger_chunk_id: null,
                        },
                        action: {
                          link_id: `${link.chunk_id}-${idx}`,
                          target_document_id: link.document_id,
                          target_chunk_id: link.chunk_id ?? null,
                          pill_position: idx,
                          hover_duration_ms: null,
                        },
                      });
                    } catch {
                      // swallow
                    }
                  }
                }}
              />
            ))}
            {hovered?.highlightId === h.highlightId && (
              <div className="absolute right-full mr-2 top-0 z-20">
                <CitePreview
                  link={slot.links[hovered.linkIndex]}
                  onOpen={() =>
                    onOpen(h.highlightId, slot.links[hovered.linkIndex])
                  }
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
