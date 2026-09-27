import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { LemonButton, LemonTag } from "../../components/lemon";
import type { BookDetail, BookSummary, FullTextResponse } from "../../api/books";
import { getBook, getBookFullText, listBooks, servabilityLabel, spinResearch } from "../../api/books";
import FloatMenu from "../shared/FloatMenu/FloatMenu";
import { useFloatMenuSelection } from "../shared/FloatMenu/useFloatMenuSelection";
import type {
  FloatMenuSelection,
  SelectionProvenance,
} from "../shared/FloatMenu/useFloatMenuSelection";
import ReadingColumn from "../../components/reader/ReadingColumn";
import { useInWindow } from "../../components/windows/windowHostContext";
import AdBorder from "./AdBorder";
import type { AdFillView } from "./AdBorder";
import ArxivFrame from "./ArxivFrame";
import Attribution from "./Attribution";
import ReadingCompanion from "./ReadingCompanion";
import ResearchThis from "./ResearchThis";
import TalkToBook from "./TalkToBook";
import TocPanel from "./TocPanel";
import VoiceNote from "./VoiceNote";
import { paginate, windowForTocPage } from "./paginate";
import { useReadingState } from "../../hooks/useReadingState";
import { useAnchors } from "../../hooks/useAnchors";
import {
  createAnchor,
  getAnchorMap,
  linkAnchorInvestigation,
  type AnchorMapChunk,
  type BookAnchor,
} from "../../lib/api";
import { buildPinBody } from "./pinBody";
import { collectAnchoredWidgets, collectDecorations } from "../../reading-physics/registry";
import { enactWidgetLayout } from "../../reading-physics/facets/anchored-widgets";
import { anchorKey } from "../../reading-physics/facets/decorations";
import { baseGeometryFromMap, createLayoutMap } from "../../reading-physics/layout-map";
import type { Rect as PhysicsRect, RenderContext } from "../../reading-physics/types";
import { makeIslandAugmentation } from "../../reading-physics/augmentations/thread-island";
import ThreadIsland from "./island/ThreadIsland";
import { deriveIslandRefs } from "./island/islandModel";
import { runSpawnFlow } from "./island/spawnFlows";
import { toast } from "../../components/lemon/LemonToast";
import {
  HIDDEN_ISLANDS_CHANGED,
  readHiddenIslands,
  unhideIsland,
} from "./island/hiddenIslands";
import type { ReadingContext } from "../../reading-physics/types";
import { makeHighlightAnchorAugmentation } from "../../reading-physics/augmentations/highlight-anchor";
import {
  anchorBodyRange,
  chunkIdAtOffset,
  normalizeNodeText,
  orphanedForList,
  rangesForPage,
} from "./anchorRanges";
import { clearReadingFocus, setReadingFocus } from "../../lib/readingFocus";
import { useReaderImpressions } from "./useReaderImpressions";
import { emitSourceRead, isRead } from "./sourceRead";

/**
 * Book reader — the Read workflow's reading surface (Read SPR-03).
 *
 * Specializes the shared reading idea for books: a TOC sidebar, page-
 * window pagination over the served markdown, prev/next, ad-border slots
 * (SPR-05) above/below the reading column (never beside it), and a
 * gate-aware body. It renders ONLY what the serve gate returns — full
 * text for a servable book, a bounded snippet for a gated one, nothing
 * for a taken-down one. The reader never decides servability; the gate
 * does, and this surface honestly reflects it.
 */

export interface BookReaderProps {
  /** Window hosts inject the document identity directly; route mounts keep
   * resolving `/read/:documentId` exactly as before. */
  documentId?: string;
  /** The reader window's origin context (reading-global SPR-02) — arrives
   * as window payload (the host spreads it into props). Metadata only: the
   * ONE consumer is the islands' dig-deeper prefill; ignoring it is lawful
   * and changes nothing. */
  origin?: { from: string; id: string } | null;
}

/** The decorations registry needs a ReadingContext; the highlight
 *  augmentation closes over its spec and never reads it (same stub the
 *  reading-physics tests use). */
const ANCHOR_STUB_CTX: ReadingContext = {
  synthesis: { question: null, claims: [] },
  layout: { resolve: () => null },
  substrate: { getChunk: () => Promise.reject(new Error("not wired in the reader")) },
};

export default function BookReader({ documentId: documentIdProp, origin = null }: BookReaderProps = {}) {
  const { documentId: routeDocumentId = "" } = useParams<{ documentId: string }>();
  const documentId = documentIdProp ?? routeDocumentId;
  const inWindow = useInWindow();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const openTalkOnLoad = searchParams.get("talk") === "1";

  const [book, setBook] = useState<BookDetail | null>(null);
  const [body, setBody] = useState<FullTextResponse | null>(null);
  const [housePool, setHousePool] = useState<BookSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const [detail, full] = await Promise.all([
          getBook(documentId),
          getBookFullText(documentId),
        ]);
        if (cancelled) return;
        setBook(detail);
        setBody(full);
        // House-state candidates for the zero-buyer ad border.
        try {
          const servable = await listBooks("servable");
          if (!cancelled) setHousePool(servable.books);
        } catch {
          /* house pool is best-effort; a neutral house card is fine */
        }
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [documentId, reloadToken]);

  const refreshSourceBody = useCallback(() => {
    setReloadToken((token) => token + 1);
  }, []);



  useEffect(() => {
    // The anchor-map is only meaningful with a readable body (the reader
    // renders only gate-served text — a gated snippet carries no anchorable
    // passages). ownerReadable is the same flag the FloatMenu outbound guard
    // uses; the owner manifest path mirrors owner-full-text.
    const readable = body?.servable || body?.reason === "owner_personal_reading";
    if (!documentId || !readable) {
      setAnchorMapChunks([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const map = await getAnchorMap(documentId, {
          owner: body?.reason === "owner_personal_reading",
        });
        if (!cancelled) setAnchorMapChunks(map.chunks);
      } catch {
        // The map is best-effort beside the body (a 403 on a just-gated book
        // must not break reading); decorations simply don't paint.
        if (!cancelled) setAnchorMapChunks([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [documentId, body]);

  // The ONE scalar space: the anchor-map's offsets and the anchor schema
  // both pin to unicode-nfc-v1 normalized text, so the body the reader
  // paginates is normalized the same way (anchorRanges.normalizeNodeText
  // mirrors substrate/feedback/domain.py:18-20).
  const normalizedBody = useMemo(
    () => normalizeNodeText(body?.full_text ?? body?.snippet ?? ""),
    [body],
  );
  const pages = useMemo(() => paginate(normalizedBody), [normalizedBody]);
  const { pageIndex, setPageIndex } = useReadingState(documentId, pages.length);

  // ── Anchored highlights (anchor-first SPR-02) ─────────────────────────
  // The owner's persisted anchors (SPR-03) and the chunk anchor-map — the
  // endpoint that finally exposes per-chunk identity for the served body,
  // closing the HONEST GAP below (was: representativeChunkId = null because
  // the books read path exposed no per-chunk id). The owner path serves the
  // manifest for personal-reading books; the public path for servable ones.
  const {
    anchors,
    refetch: refetchAnchors,
    remove: removeAnchor,
  } = useAnchors(documentId);
  const [anchorMapChunks, setAnchorMapChunks] = useState<AnchorMapChunk[]>([]);
  const anchorChunksById = useMemo(() => {
    const byId = new Map<string, AnchorMapChunk>();
    for (const chunk of anchorMapChunks) byId.set(chunk.chunk_id, chunk);
    return byId;
  }, [anchorMapChunks]);

  // ── Research-thread islands (island SPR-02) ───────────────────────────
  // Islands are the thread-linked anchors (SPR-01's deriveIslandRefs). An
  // island SUPERSEDES a plain highlight mark: the unit-1 wash + underline
  // already paints its anchor; this widget adds the live status glyph and
  // the pinned overlay card. Orphaned islands follow the parent's rule
  // (nothing in the body, one honest list row).
  const islands = useMemo(() => deriveIslandRefs(anchors), [anchors]);

  // The per-device "hide" preference (client-side only; never deletes
  // anything). Re-read on the module's change event so Hide/Unhide both
  // reflect immediately.
  const [hiddenIslands, setHiddenIslands] = useState<Set<string>>(() =>
    readHiddenIslands(),
  );
  useEffect(() => {
    function sync() {
      setHiddenIslands(readHiddenIslands());
    }
    window.addEventListener(HIDDEN_ISLANDS_CHANGED, sync);
    return () => window.removeEventListener(HIDDEN_ISLANDS_CHANGED, sync);
  }, []);

  const visibleIslands = useMemo(
    () => islands.filter((i) => !hiddenIslands.has(i.anchorId)),
    [islands, hiddenIslands],
  );

  // The widget surface: pin each visible island through the reading-physics
  // plan (declare), resolve geometry from the island's mark span (the ONE
  // place pixels are measured — the surface owns the read, PR-4), and enact
  // the widgets over the reading column. An island whose anchor isn't laid
  // out (off-page, orphaned) resolves null and renders nothing — the
  // LayoutMap contract, never a fabricated position.
  const mainRef = useRef<HTMLElement>(null);
  const [islandRects, setIslandRects] = useState<ReadonlyMap<string, PhysicsRect>>(
    () => new Map(),
  );
  useEffect(() => {
    const main = mainRef.current;
    if (!main || visibleIslands.length === 0) {
      setIslandRects(new Map());
      return;
    }
    function measure() {
      const mainRect = main!.getBoundingClientRect();
      const next = new Map<string, PhysicsRect>();
      for (const island of visibleIslands) {
        const key = anchorKey({
          kind: "passage",
          chunkId: island.passageAnchor.chunkId as never,
          start: island.passageAnchor.start,
          end: island.passageAnchor.end,
        });
        const span = main!.querySelector(`[data-anchor-id="${island.anchorId}"]`);
        if (span) {
          const r = span.getBoundingClientRect();
          next.set(key, {
            top: r.top - mainRect.top,
            left: r.left - mainRect.left,
            width: r.width,
            height: r.height,
          });
        }
      }
      setIslandRects(next);
    }
    measure();
    // jsdom has no ResizeObserver: the one measurement per pass stands there
    // (repagination re-runs this effect anyway); real browsers get live
    // resize tracking too.
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(main);
    return () => observer.disconnect();
  }, [visibleIslands, pageIndex, pages, anchors, anchorMapChunks]);

  const islandLayoutMap = useMemo(
    () => createLayoutMap(baseGeometryFromMap(islandRects)),
    [islandRects],
  );

  const enactedIslands = useMemo(() => {
    if (visibleIslands.length === 0) return [];
    const augmentations = visibleIslands.map((island) =>
      makeIslandAugmentation({
        anchorId: island.anchorId,
        documentId: island.documentId,
        chunkId: island.passageAnchor.chunkId,
        start: island.passageAnchor.start,
        end: island.passageAnchor.end,
        investigationId: island.investigationId,
        servable: island.servable,
        passageQuote: island.servable
          ? anchors.find((a) => a.anchor_id === island.anchorId)?.anchor.quote || null
          : null,
        pageIndexHint:
          anchors.find((a) => a.anchor_id === island.anchorId)?.page_index_hint ?? null,
        origin,
      }),
    );
    const plan = collectAnchoredWidgets(augmentations, ANCHOR_STUB_CTX);
    return enactWidgetLayout(plan, islandLayoutMap);
  }, [visibleIslands, anchors, islandLayoutMap, origin]);

  const islandRenderCtx: RenderContext = useMemo(
    () => ({
      pass: "main",
      layout: islandLayoutMap,
      components: { ThreadIsland },
    }),
    [islandLayoutMap],
  );

  // Citation → page jump (M2). A talk-to-book / search citation carries a
  // resolved 0-based page; map it to the window index and move the reader.
  // REUSES the EXISTING reader navigation (windowForTocPage + setPageIndex) —
  // the SAME path TOC jumps use, not a parallel one.
  const jumpToPage = useCallback(
    (page: number) => {
      const window = windowForTocPage(pages, page);
      if (window !== null) setPageIndex(window);
    },
    [pages, setPageIndex],
  );

  // Reader ad-impression flushing (SPR-05). A stable session id per mount;
  // the hook tracks focused dwell and flushes the page's slots on change.
  const [sessionId] = useState(
    () =>
      "rs-" +
      (typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID().replace(/-/g, "").slice(0, 12)
        : Math.random().toString(36).slice(2, 14)),
  );
  // The book's reading thread (Read SPR-06). One id ties the companion's
  // notes, the reader's voice notes, the in-book float-menu NOTE, the
  // source.read history, and the floating chase parent together — they all
  // read/append to the same thread. Not a user-facing label (copy-lint): it is
  // passed to components, never rendered.
  const readingThreadId = `read-${documentId}`;

  // §9.0 — the chunk the read/note is attributed to.
  //
  // THE HONEST GAP, CLOSED (anchor-first SPR-02): this used to record null
  // because the books read path exposed no per-chunk id for the linear body.
  // The SPR-03 anchor-map now serves exactly that (chunk_id → body offsets),
  // so a selection's chunk resolves for real — by locating the selected text
  // in the current page and mapping the offset through the manifest. A
  // selection that doesn't locate uniquely still records null HONESTLY
  // (never a fabricated coverage claim).
  const ownerReadable =
    book?.servable_full_text === true || body?.reason === "owner_personal_reading";

  // source.read (SPR-07 M4) — fire ONCE per source per reading session on the
  // justified dwell threshold, reusing the focused-dwell clock the ad-impression
  // tracker already runs. A per-session guard (ref) coalesces it: never per-page
  // spam, never refired. §9.0: the event carries no body (sourceRead.ts).
  const readEmittedRef = useRef(false);
  // The current page's chunk for the source.read event — resolved live from
  // the anchor-map (the HONEST GAP closure), never the old null placeholder.
  const pageChunkRef = useRef<string | null>(null);
  const onDwell = useCallback(
    (dwell: { totalDwellMs: number; pagesSeen: number }) => {
      if (readEmittedRef.current) return;
      if (!isRead(dwell.totalDwellMs, dwell.pagesSeen)) return;
      readEmittedRef.current = true;
      void emitSourceRead({
        documentId,
        readingThreadId,
        chunkId: pageChunkRef.current,
        dwellMs: dwell.totalDwellMs,
        pageCount: dwell.pagesSeen,
      });
    },
    [documentId, readingThreadId],
  );
  const { observePage } = useReaderImpressions(documentId, sessionId, onDwell);
  const [showVoice, setShowVoice] = useState(false);

  // ── In-book SPR-04 float-menu host (SPR-07 M2) ───────────────────────────
  // The reader is the HOST for the SAME shared FloatMenu Research uses — it is
  // REUSED, not re-implemented (verify by import: ../shared/FloatMenu/FloatMenu).
  // The page <article> is the selection SCOPE; `resolveProvenance` resolves the
  // book selection's document + its §9.0 servable flag so the menu's outbound
  // chokepoint can refuse a withheld selection. The in-book highlight→action
  // (the old inline "Go deeper" affordance) is GENERALIZED through this menu:
  // Deep-research (highlight) used to open ChaseThread without book provenance;
  // that path never hit spin-research / notebook distill. Wire to spin-research.

  const articleRef = useRef<HTMLElement>(null);

  // §9.0 servability of the open book — the in-book selection's servability.
  // The reader renders only gate-served body (verified: getBookFullText returns
  // full_text:null for a gated/taken-down book), so `book.servable_full_text`
  // IS the selection's servable flag: a selection can only be from text the gate
  // served. We pass it through so the FloatMenu chokepoint refuses Search/Deep-
  // research over a non-servable book (defence in depth — the body can't even
  // reach the DOM, but the outbound guard holds regardless).
  // Owner-readable personal_reading has full body via owner-full-text but
  // book.servable_full_text stays false (public gate). Treat ownerReadable as
  // servable for FloatMenu outbound so highlight → Deep-research works in
  // dogfood without weakening the public /full-text contract.
  const resolveProvenance = useCallback(
    (_range: Range, text: string): SelectionProvenance => {
      const chunkId = resolveSelectionChunk(text);
      return { documentId, chunkId, servable: ownerReadable };
    },
    // resolveSelectionChunk is defined below (after the page locator helpers);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [documentId, ownerReadable, anchorMapChunks, normalizedBody, pageIndex, pages],
  );

  // TP SERVABLE mount — BEFORE any early returns (Rules of Hooks).
  // Gated books never publish page body (dual structure / issue-3135 class).
  useEffect(() => {
    if (!documentId) {
      clearReadingFocus();
      return;
    }
    const pageText =
      ownerReadable && pages[pageIndex]?.text
        ? pages[pageIndex].text
        : null;
    setReadingFocus({
      documentId,
      pageIndex,
      title: book?.title ?? null,
      pageText,
      servable: ownerReadable,
    });
    return () => {
      clearReadingFocus();
    };
  }, [documentId, pageIndex, book?.title, ownerReadable, pages]);


  const selection = useFloatMenuSelection({
    scopeRef: articleRef,
    resolveProvenance,
    minLength: 8,
  });

  // ── Pin machinery (anchor-first SPR-02) ───────────────────────────────
  // Locate the selected text UNIQUELY in the current page, then map the page
  // offset through the anchor-map to a chunk + chunk-relative offsets. A
  // non-unique or cross-chunk match resolves null — never a guessed anchor.
  const locateSelection = useCallback(
    (
      text: string,
    ): { chunkId: string; start: number; end: number; bodyOffset: number } | null => {
      const page = pages[pageIndex];
      if (!page || !text) return null;
      const first = page.text.indexOf(text);
      if (first < 0 || page.text.indexOf(text, first + 1) >= 0) return null;
      const bodyOffset = page.bodyStart + first;
      const end = bodyOffset + text.length;
      const chunkId = chunkIdAtOffset(bodyOffset, anchorMapChunks);
      if (!chunkId) return null;
      const chunk = anchorChunksById.get(chunkId);
      if (!chunk || end > chunk.body_end) return null; // cross-chunk selection
      return { chunkId, start: bodyOffset - chunk.body_start, end: end - chunk.body_start, bodyOffset };
    },
    [pages, pageIndex, anchorMapChunks, anchorChunksById],
  );

  const resolveSelectionChunk = useCallback(
    (text: string): string | null => locateSelection(text)?.chunkId ?? null,
    [locateSelection],
  );

  // Persist one anchor from a selection. Returns the stored row (null on an
  // honest no-location). The §9.0 rule at the pin boundary: a WITHHELD
  // selection's text never leaves the client — it resolves LOCALLY via the
  // anchor-map and posts ids+numbers only (the explicit metadata-only form);
  // a servable selection posts the quote and the server resolves canonically.
  const pinFromSelection = useCallback(
    async (source: string, sel: FloatMenuSelection): Promise<BookAnchor | null> => {
      const loc = locateSelection(sel.text);
      const body = buildPinBody(source, sel, loc, normalizedBody, pageIndex);
      if (!body) return null;
      return createAnchor(documentId, body);
    },
    [documentId, pageIndex, locateSelection, normalizedBody],
  );

  // The FloatMenu's pin seam: Note/Dialogue/Search + the Pin button fire here
  // (Deep-research pins inside onDeepResearch below — the SPR-04 write-back
  // needs the anchor id). Auto-pins are best-effort beside their action: a
  // failed pin never breaks the action (it is logged, never surfaced as if
  // the action failed); the manual Pin is surfaced honestly.
  const onPinAnchor = useCallback(
    (pin: { source: string }, sel: FloatMenuSelection) => {
      void (async () => {
        try {
          await pinFromSelection(pin.source, sel);
          refetchAnchors();
        } catch (e) {
          console.warn(`anchor pin (${pin.source}) failed`, e);
        }
      })();
    },
    [pinFromSelection, refetchAnchors],
  );

  // Deep-research (highlight) -> pin -> spin-research -> write-back, and the
  // ISLAND emerges collapsed at the passage (island SPR-03) — the reader does
  // NOT navigate away; "Open research" on the island is the explicit jump.
  // Book-bound provenance via POST /books/{id}/spin-research. ChaseThread
  // stays the in-investigation chase path on the Research workstation.
  // Section 9.0: null safeSpawnText = refuse. First link wins — a second
  // spawn never overwrites. The failure matrix (pin / spawn / link) surfaces
  // honestly, never an anchorless island.
  const onDeepResearch = useCallback(
    (safeSpawnText: string | null, sel: FloatMenuSelection) => {
      if (safeSpawnText === null) return;
      window.getSelection()?.removeAllRanges();
      const loc = locateSelection(sel.text);
      void (async () => {
        const result = await runSpawnFlow({
          anchors,
          locate: () => loc,
          pin: async () => {
            const pinned = await pinFromSelection("floatmenu_deep_research", sel);
            if (!pinned) throw new Error("the passage could not be anchored");
            return pinned;
          },
          spin: (passageText) => spinResearch(documentId, pageIndex, passageText),
          link: (anchorId, investigationId) =>
            linkAnchorInvestigation(documentId, anchorId, investigationId),
          passageText: safeSpawnText,
        });
        if (result.ok) {
          refetchAnchors();
          toast.info("Research started — the island is on your passage.");
        } else {
          toast.warn(result.message ?? "Couldn't start the research.");
          refetchAnchors(); // a lawful pinned highlight may remain
        }
      })();
    },
    [documentId, pageIndex, anchors, locateSelection, pinFromSelection, refetchAnchors],
  );

  // Free-inquiry (island SPR-03): pin the current page's LEAD passage first
  // (source=pin), then spin with the pinned passage, then the island. The
  // same dedupe + failure matrix as the highlight path; a gated book's
  // passage can't anchor (no manifest) and refuses honestly with no withheld
  // text anywhere.
  const spawnFreeInquiry = useCallback(() => {
    const page = pages[pageIndex];
    if (!page) return;
    const lead = page.text.split(/\n{2,}/).map((b) => b.trim()).find(Boolean);
    if (!lead) return;
    const startInPage = page.text.indexOf(lead);
    const bodyOffset = page.bodyStart + startInPage;
    const chunkId = chunkIdAtOffset(bodyOffset, anchorMapChunks);
    const chunk = chunkId ? anchorChunksById.get(chunkId) : undefined;
    const loc = chunk
      ? {
          chunkId: chunk.chunk_id,
          start: bodyOffset - chunk.body_start,
          end: bodyOffset + lead.length - chunk.body_start,
        }
      : null;
    void (async () => {
      const servableForOutbound = ownerReadable;
      const result = await runSpawnFlow({
        anchors,
        locate: () => loc,
        pin: async () => {
          if (!loc || !chunkId) throw new Error("the passage could not be anchored");
          if (servableForOutbound) {
            return createAnchor(documentId, {
              quote: lead,
              prefix: normalizedBody.slice(Math.max(0, bodyOffset - 32), bodyOffset),
              suffix: normalizedBody.slice(bodyOffset + lead.length, bodyOffset + lead.length + 32),
              page_index_hint: pageIndex,
              source: "pin",
            });
          }
          // Metadata-only (owner-readable withheld book): ids/numbers only —
          // the passage text never leaves the client in the pin.
          return createAnchor(documentId, {
            node_id: chunkId,
            start_scalar: loc.start,
            end_scalar: loc.end,
            page_index_hint: pageIndex,
            source: "pin",
          });
        },
        spin: (passageText) => spinResearch(documentId, pageIndex, passageText),
        link: (anchorId, investigationId) =>
          linkAnchorInvestigation(documentId, anchorId, investigationId),
        passageText: lead,
      });
      if (result.ok) {
        refetchAnchors();
        toast.info("Research started — the island is on your passage.");
      } else {
        toast.warn(result.message ?? "Couldn't start the research.");
        refetchAnchors();
      }
    })();
  }, [documentId, pageIndex, pages, anchors, anchorMapChunks, anchorChunksById, normalizedBody, ownerReadable, refetchAnchors]);

  // Turning the page (or jumping via TOC) collapses a stale selection — the
  // anchored menu would otherwise float over the wrong page. A chase already in
  // flight is left alone (it owns its passage, page-independent).
  useEffect(() => {
    window.getSelection()?.removeAllRanges();
  }, [pageIndex]);

  // Zero-buyer house fill: promote a servable book that isn't this one.
  const houseFill = useMemo<AdFillView>(() => {
    const candidate = housePool.find((b) => b.document_id !== documentId);
    return {
      kind: "house",
      house: candidate
        ? {
            documentId: candidate.document_id,
            title: candidate.title ?? candidate.document_id,
            author: candidate.author,
          }
        : null,
    };
  }, [housePool, documentId]);

  const openHouse = useCallback(
    (docId: string) => navigate(`/read/${encodeURIComponent(docId)}`),
    [navigate],
  );

  // The decorations pipeline (anchor-first SPR-02): each persisted anchor
  // declares a decoration through the highlight augmentation (declare), the
  // registry combines (dedup/union on the same range), and the surface maps
  // the resolved decorations to inline painted marks (enact). Orphaned
  // anchors never paint — they list honestly below instead.
  const pageMarks = useMemo(() => {
    const current = pages[pageIndex];
    if (!current || anchors.length === 0 || anchorMapChunks.length === 0) return [];
    const paintable = anchors.filter(
      (a) => a.status !== "orphaned" && anchorBodyRange(a, anchorChunksById),
    );
    if (paintable.length === 0) return [];
    // DECLARE: each anchor declares its decoration through the highlight
    // augmentation (the spec's declaration layer); the registry COMBINES
    // (same-range union, order-independent). The combine output is the paint
    // set — the tuples to mark.
    const augmentations = paintable.map((a) =>
      makeHighlightAnchorAugmentation({
        anchorId: a.anchor_id,
        chunkId: a.anchor.node_id,
        start: a.anchor.start_scalar,
        end: a.anchor.end_scalar,
        treatment: a.status === "drifted" ? "drifted" : "active",
        title:
          a.status === "drifted"
            ? "Moved — re-anchored here after the text changed"
            : "Anchored highlight",
      }),
    );
    const resolved = collectDecorations(augmentations, ANCHOR_STUB_CTX);
    const paintKeys = new Set(
      resolved.flatMap((d) =>
        d.anchor.kind === "passage"
          ? [`${d.anchor.chunkId}:${d.anchor.start}:${d.anchor.end}`]
          : [],
      ),
    );
    // ENACT: the registry-selected tuples, mapped through the anchor-map's
    // body geometry (chunk-relative → body → page-relative — rangesForPage's
    // tested math), painted inline.
    const matched = paintable.filter((a) =>
      paintKeys.has(
        `${a.anchor.node_id}:${a.anchor.start_scalar}:${a.anchor.end_scalar}`,
      ),
    );
    return rangesForPage(current, matched, anchorChunksById);
  }, [anchors, anchorMapChunks, anchorChunksById, pages, pageIndex]);

  const orphanedAnchors = useMemo(() => orphanedForList(anchors), [anchors]);

  // Tell the impression tracker which slots are showing on this page. It
  // flushes the previous page's impressions (with focused dwell) when the
  // page changes. Runs only once the body has paginated.
  useEffect(() => {
    if (pages.length === 0) return;
    // Only register impression slots for the rails we actually render. The
    // discriminating gate is `body.ad_eligible` AND having a paginated body:
    //   • an ad-eligible body WITH pages shows top+bottom AdBorders, so it
    //     registers their slots (they record impressions);
    //   • a non-ad-eligible body (arXiv T2/T3, or any non-ad-eligible work)
    //     shows no rails, so it registers NO slots — never a FALSE impression
    //     for a rail that isn't on screen. This is load-bearing: a non-ad-
    //     eligible doc registering slots would flush false impressions straight
    //     into the SPR-06 accrual/money path.
    //   • a content-gated ad-eligible doc whose body isn't stored yet
    //     (ad_eligible true, full_text null → pages.length 0) is already
    //     excluded by the early return above; the `pages.length > 0` here
    //     mirrors the RENDER gate so the two never disagree.
    // The empty observe (`[]`) still drives the prev-page flush.
    const base = `slot:${documentId}:p${pageIndex}`;
    observePage(
      pageIndex,
      body?.ad_eligible && pages.length > 0
        ? [
            { slotId: `${base}:top`, fill: houseFill },
            { slotId: `${base}:bottom`, fill: houseFill },
          ]
        : [],
    );
  }, [pageIndex, houseFill, documentId, pages.length, observePage, body?.ad_eligible]);

  if (loading) {
    return <CenterNote inWindow={inWindow}>Opening the book…</CenterNote>;
  }
  if (error || !book || !body) {
    return (
      <CenterNote tone="error" inWindow={inWindow}>
        {error === "book_not_found" ? "That book isn't in the library." : error}
      </CenterNote>
    );
  }

  const { label, colour } = servabilityLabel(book.servability);
  const page = pages[pageIndex];
  pageChunkRef.current = page ? chunkIdAtOffset(page.bodyStart, anchorMapChunks) : null;



  const slotBase = `slot:${documentId}:p${pageIndex}`;

  // ── Rights-tiered reader branch (Read SPR-05) ────────────────────────────
  // Data-driven: read tier / ad-eligibility / canonical link off the GATE
  // response (never a local flag — rigor #5). `tier === null` ⇒ a non-arXiv
  // document, which stays on exactly today's path (the else-branch below, with
  // ad rails gated on `ad_eligible`, which the backend sets == servable for
  // non-arXiv, so it is unchanged). An arXiv T2 (gated, no hosted body) or T3
  // (unknown/default) renders the link-back ArxivFrame with NO body and NO ad
  // slots; only a redistributable arXiv T1 (hosted extracted text) and every
  // non-arXiv book take the hosted-body path.
  const isArxiv = body.tier !== null;
  // An arXiv T2/T3 doc reads on arXiv. The normal case has a canonical_url (the
  // gate stamps arxiv_id + license_uri together on persist, so it is co-present
  // in practice). The link-back frame needs that URL.
  const isArxivT2T3 = isArxiv && (body.tier === "T2" || body.tier === "T3");
  const isArxivLinkBack = isArxivT2T3 && body.canonical_url !== null;
  // Defence-in-depth: an arXiv T2/T3 doc that somehow lost its canonical_url
  // (UNREACHABLE from the OAI persist path, where arxiv_id is co-stamped with
  // license_uri) must NOT fall through to the hosted-body else-branch — that
  // would render an empty body with no link-back (an M3 violation for that
  // input). Degrade honestly: show the "read on arXiv (link unavailable)"
  // notice, NO body, NO ad rails.
  const isArxivLinkUnavailable = isArxivT2T3 && body.canonical_url === null;
  // Ad rails (and their impression slots) render only when the body is BOTH
  // ad-eligible AND actually paginated. A content-gated arXiv T1 (ad_eligible
  // true, but body not yet stored → full_text null → pages.length 0) must NOT
  // mount empty rails around nothing. Reads ad-eligibility off the gate body
  // (never a local flag); `pages.length > 0` is the body-present condition.
  const adEligible = body.ad_eligible && pages.length > 0;

  return (
    <div
      data-testid="book-reader-root"
      className={`flex ${inWindow ? "h-full bg-transparent" : "h-full bg-ice-0 dark:bg-charcoal-2"}`}
    >
      {/* TOC sidebar */}
      <aside className="w-64 flex-shrink-0 border-r border-rule dark:border-charcoal-1 overflow-y-auto p-3 hidden md:block">
        <p className="font-serif text-sm text-ink dark:text-bright mb-1 truncate">
          {book.title ?? documentId}
        </p>
        <p className="text-xs font-mono text-shadow-1 dark:text-moonlight mb-3 truncate">
          {book.author ?? "Unknown author"}
        </p>
        <TocPanel toc={book.toc} currentPageIndex={pageIndex} onJump={setPageIndex} />
        {(orphanedAnchors.length > 0 || hiddenIslands.size > 0) && (
          <div
            className="mt-3 border-t border-rule dark:border-charcoal-1 pt-2"
            data-anchor-list
          >
            <p className="text-xxs uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-1">
              Anchors
            </p>
            {orphanedAnchors.map((a) => (
              <div
                key={a.anchor_id}
                data-orphaned-anchor={a.anchor_id}
                className="flex items-center gap-1 py-0.5 text-xs text-shadow-1 dark:text-moonlight"
              >
                <span className="min-w-0 truncate">
                  {a.page_index_hint !== null ? `Page ${a.page_index_hint + 1} · ` : ""}
                  text no longer found
                </span>
                {a.investigation_id ? (
                  <Link
                    to={`/inv/${encodeURIComponent(a.investigation_id)}`}
                    className="shrink-0 text-sun-deep hover:underline"
                    title="Open the research thread (the anchor's text is gone; the thread is untouched)"
                    data-orphaned-island-open
                  >
                    →
                  </Link>
                ) : null}
                <button
                  type="button"
                  aria-label={`Delete orphaned anchor on page ${
                    a.page_index_hint !== null ? a.page_index_hint + 1 : "?"
                  }`}
                  className="shrink-0 px-0.5 text-shadow-1 hover:text-ink dark:hover:text-bright"
                  onClick={() => void removeAnchor(a.anchor_id)}
                >
                  ×
                </button>
              </div>
            ))}
            {islands
              .filter((i) => hiddenIslands.has(i.anchorId))
              .map((i) => (
                <div
                  key={i.anchorId}
                  data-hidden-island={i.anchorId}
                  className="flex items-center gap-1 py-0.5 text-xs text-shadow-1 dark:text-moonlight"
                >
                  <span className="min-w-0 truncate italic">hidden island</span>
                  <button
                    type="button"
                    aria-label="Show this island again on this device"
                    className="shrink-0 text-sun-deep hover:underline"
                    onClick={() => unhideIsland(i.anchorId)}
                  >
                    show again
                  </button>
                </div>
              ))}
          </div>
        )}
      </aside>

      {/* In-book SPR-04 float-menu (SPR-07 M2). Highlighting any passage in the
          page <article> opens the SAME {Note · Dialogue · Search · Deep-research}
          float component the Research surface uses — REUSED, not re-implemented.
          It replaces the old single-action "Go deeper" toolbar (generalized:
          Deep-research IS the rabbit-hole, now one of four consistent actions).
          NOTE is scoped to the book's reading thread (M3): it lands in the
          companion (deriveNotes renders marginalia.noted as a USER-sourced
          note) AND is promoted host-side into a user-authored per-book insight
          node grounded on this document, so a later block_search returns it
          (substrate/graph/insight_question.promote_from_marginalia_event; the
          /events/typed endpoint promotes on emit, backfill is the safety net).
          §9: source_kind "user" is carried onto the node — never conflated with
          a model-emerged insight. Deep-research spins book-bound research and
          the island emerges on the passage (island SPR-03 — no navigate-away).
          §9.0: the outbound chokepoint refuses Search/Deep-research
          over a non-servable book. */}
      <FloatMenu
        selection={selection}
        investigationId={readingThreadId}
        onDeepResearch={onDeepResearch}
        onPinAnchor={onPinAnchor}
      />


      {/* Reading column */}
      <main ref={mainRef} className="relative flex-1 overflow-y-auto">
        {/* The island widget layer (SPR-02): anchored widgets enacted over the
            reading column at their layout-map rects. Pointer-events pass
            through except on the widgets themselves — the SAME pattern as the
            floating layer. NEVER a workspace window. */}
        {enactedIslands.length > 0 && (
          <div className="absolute inset-0 pointer-events-none z-20" data-island-layer>
            {enactedIslands.map((enacted) =>
              enacted.rect ? (
                <div
                  key={enacted.widget.id}
                  className="absolute pointer-events-auto"
                  style={{
                    top: enacted.rect.top,
                    left: enacted.rect.left + enacted.rect.width,
                  }}
                >
                  {enacted.widget.render(enacted.rect, islandRenderCtx)}
                </div>
              ) : null,
            )}
          </div>
        )}
        <div className="max-w-2xl mx-auto px-6 py-6 flex flex-col gap-4 min-h-full">
          <header className="flex items-center justify-between gap-3">
            <h1 className="text-xl font-serif text-ink dark:text-bright truncate">
              {book.title ?? documentId}
            </h1>
            <LemonTag colour={colour} dot>
              {label}
            </LemonTag>
          </header>

          {isArxivLinkBack ? (
            /* arXiv T2/T3 — the gated / unknown-rights tiers. Antiek hosts NO
               body and serves NO ads here (body-serving + ad-eligibility are
               {T1}-only, per the binding rights law). The reader renders the
               link-back ArxivFrame (pointing at the gate-served canonical_url)
               + the Attribution chrome, and nothing else: no ReadingColumn body,
               no AdBorder slots, no in-book page actions. The iframe inside the
               frame, if it loads at all, loads browser→arXiv — Antiek never
               proxies arXiv bytes. The only thing that differs between T2 and T3
               is the attribution label (handled inside ArxivFrame/Attribution). */
            <ArxivFrame
              canonicalUrl={body.canonical_url as string}
              title={book.title}
              author={book.author}
              tier={body.tier as "T2" | "T3"}
            />
          ) : isArxivLinkUnavailable ? (
            /* Degenerate arXiv T2/T3 with no canonical_url (defence-in-depth;
               unreachable from the OAI persist path). Antiek hosts NO body for
               these tiers and has no link to offer — so we render an HONEST
               notice and nothing else: no empty ReadingColumn, no AdBorder
               rails. This degrades the M3 contract gracefully rather than
               falling through to an empty hosted-body view. */
            <div
              data-arxiv-link-unavailable
              className="text-sm border-edge border-sun rounded-md bg-sun/15 px-3 py-2 text-ink dark:text-bright"
            >
              This paper is read on arXiv, but its arXiv link isn’t available
              right now. Try again later or search arXiv for the title above.
            </div>
          ) : (
            <>
              {!ownerReadable && (
                <div className="text-sm border-edge border-sun rounded-md bg-sun/15 px-3 py-2 text-ink dark:text-bright">
                  {book.servability === "taken_down"
                    ? "This title has been removed and is no longer available to read."
                    : "Preview only — this title isn’t licensed for full reading. You’re seeing a short snippet and its metadata."}
                </div>
              )}

              {/* Ad-border (top) — gated on `body.ad_eligible` (Read SPR-05 M4).
                  The backend computes ad-eligibility regression-safely: arXiv →
                  {T1}-only; non-arXiv → == servable (today's behaviour). So a
                  non-arXiv servable book keeps its rails (unchanged), an arXiv T1
                  gets rails, and any non-ad-eligible body shows NO rails. The fill
                  is still the zero-buyer house PLACEHOLDER (no live ad serving /
                  revenue math this sprint — that's SPR-06+/Phase 4, gated G2/G3). */}
              {adEligible && (
                <AdBorder slotId={`${slotBase}:top`} position="top" fill={houseFill} onOpenHouse={openHouse} />
              )}

              {/* Page body + the in-book float-menu SCOPE (M2) + the SPR-07
                  attribution markers (SPR-09 M3). The shared useFloatMenuSelection
                  hook listens on `selectionchange` and opens the menu only for
                  selections inside this <article>; ReadingColumn forwards the ref so
                  that scope is preserved verbatim. The load-bearing addition: when
                  the gate served full text (a SERVABLE asset), the column carries
                  `data-akb-asset-id={documentId}` so SPR-07's shell-level
                  useFrameAttention — which scans the working region for
                  [data-akb-asset-id] — finally detects an in-frame IP asset and the
                  per-second telemetry stops being all-house-seconds. §9.0: a gated /
                  taken-down work never reaches here with a body (the snippet path
                  below renders the notice), so a tagged column is only ever a
                  servable asset; attribution can never accrue to withheld text. We
                  pass no chunkId — the books read path exposes no per-chunk id for
                  the linear body, and we never fabricate one (asset-level is
                  correct, per the contract's cover/title-card case). For an arXiv
                  T1 the gate served extracted hosted TEXT (no PDF blob exists —
                  see docs/decisions/arxiv-t1-hosted-text-not-pdf.md), so it renders
                  through this SAME markdown column, no PDF.js. */}
              <ReadingColumn
                ref={articleRef}
                assetId={ownerReadable ? documentId : null}
                chunkId={
                  page ? chunkIdAtOffset(page.bodyStart, anchorMapChunks) : null
                }
                text={page?.text ?? ""}
                contentFormat={body.content_format ?? "text"}
                marks={pageMarks}
              />

              {/* Per-page actions: voice note + spin a deep research. */}
              {page && (
                <div className="space-y-2">
                  <div className="flex items-center justify-end gap-2">
                    <LemonButton
                      type="button"
                      variant="tertiary"
                      size="sm"
                      aria-pressed={showVoice}
                      onClick={() => setShowVoice((v) => !v)}
                    >
                      {showVoice ? "Close voice note" : "＋ Voice note"}
                    </LemonButton>
                    <LemonButton
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={spawnFreeInquiry}
                      title="Pin this page's lead passage and start a research thread on it — the island stays on the passage"
                    >
                      Research from here
                    </LemonButton>
                    <ResearchThis documentId={documentId} pageIndex={pageIndex} passageText={selection?.text ?? page.text} />
                  </div>
                  {showVoice && (
                    <VoiceNote
                      documentId={documentId}
                      pageIndex={pageIndex}
                      investigationId={readingThreadId}
                    />
                  )}
                </div>
              )}

              {/* Ad-border (bottom) — gated on `body.ad_eligible` (M4). */}
              {adEligible && (
                <AdBorder slotId={`${slotBase}:bottom`} position="bottom" fill={houseFill} onOpenHouse={openHouse} />
              )}
            </>
          )}

          {/* Attribution (M3) — renders on ALL branches: it tells the reader
              where the work came from + under what license. For an arXiv doc it
              shows the canonical "via arXiv" link + tier/license chips; for a
              non-arXiv doc it renders nothing extra (the servability badge above
              stays the rights cue). Reads tier/canonical/license off the gate
              response, never a local flag. */}
          <Attribution body={body} />

          {/* Pager — hidden on the link-back branch (no hosted pages there). */}
          {!isArxivLinkBack && pages.length > 0 && (
            <nav className="flex items-center justify-between border-t border-rule dark:border-charcoal-1 pt-3">
              <LemonButton
                size="sm"
                type="button"
                disabled={pageIndex <= 0}
                onClick={() => setPageIndex(pageIndex - 1)}
              >
                ← Previous
              </LemonButton>
              <span className="text-xs font-mono text-shadow-1 dark:text-moonlight">
                {page ? `Page ${page.pageNumber}` : "—"} of {pages.length}
              </span>
              <LemonButton
                size="sm"
                type="button"
                disabled={pageIndex >= pages.length - 1}
                onClick={() => setPageIndex(pageIndex + 1)}
              >
                Next →
              </LemonButton>
            </nav>
          )}
        </div>
      </main>

      {/* The Read glass-box (M2) stays available while highlight chases open in
          floating workspace chrome. The page never moves (usePosition), so a
          reader can inspect a spawned chase and keep the book context intact. */}
      <ReadingCompanion
        documentId={documentId}
        title={book.title}
        readingThreadId={readingThreadId}
        onSourceBodyChanged={refreshSourceBody}
      />


      {/* M2 — the floating bookmark: a book-level MULTI-TURN talk-to-book
          conversation that persists across page navigation (session state, the
          usePosition precedent). Answers cite pages → jumpToPage moves the
          SPR-07 reader. The SPR-04 selection FloatMenu Dialogue stays one-shot;
          THIS is the new multi-turn surface. */}
      <TalkToBook
        documentId={documentId}
        title={book.title}
        initialOpen={openTalkOnLoad}
        onJumpToPage={jumpToPage}
      />
    </div>
  );
}

function CenterNote({
  children,
  tone,
  inWindow = false,
}: {
  children: React.ReactNode;
  tone?: "error";
  inWindow?: boolean;
}) {
  return (
    <div
      data-testid="book-reader-status"
      className={`${inWindow ? "h-full bg-transparent" : "h-full bg-ice-0 dark:bg-charcoal-2"} flex items-center justify-center`}
    >
      <p
        className={`text-sm font-serif ${
          tone === "error" ? "text-emperor" : "text-shadow-1 dark:text-moonlight italic"
        }`}
      >
        {children}
      </p>
    </div>
  );
}
