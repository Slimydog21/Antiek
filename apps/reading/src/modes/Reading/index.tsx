import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { LemonButton, LemonTag } from "../../components/lemon";
import type { BookDetail, BookSummary, FullTextResponse, TocItem } from "../../api/books";
import { getBook, getBookFullText, listBooks, servabilityLabel } from "../../api/books";
import FloatMenu from "../shared/FloatMenu/FloatMenu";
import { useFloatMenuSelection } from "../shared/FloatMenu/useFloatMenuSelection";
import type {
  FloatMenuSelection,
  SelectionProvenance,
} from "../shared/FloatMenu/useFloatMenuSelection";
import ChaseThread from "../ResearchWorkstation/ChaseThread";
import ReadingColumn from "../../components/reader/ReadingColumn";
import Reader, { deriveToc } from "../../components/reader/Reader";
import ReaderErrorBoundary from "../../components/reader/ReaderErrorBoundary";
import { allBlockTypesKnown } from "../../components/reader/knownBlockTypes";
import { openDocumentStub } from "../../components/reader/openDocumentStub";
import PdfViewer from "../../components/PdfViewer";
import type { Block, Document, InlineSpan, TocEntry } from "../../types/document_model.gen";
import { paginateBlocks, windowForBlockIndex } from "./paginateBlocks";
import AdBorder from "./AdBorder";
import type { AdFillView } from "./AdBorder";
import ArxivFrame from "./ArxivFrame";
import Attribution from "./Attribution";
import ReadingCompanion from "./ReadingCompanion";
import ResearchThis from "./ResearchThis";
import TalkToBook from "./TalkToBook";
import TocPanel from "./TocPanel";
import VoiceNote from "./VoiceNote";
import { paginate } from "./paginate";
import { usePosition } from "./usePosition";
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

export default function BookReader() {
  const { documentId = "" } = useParams<{ documentId: string }>();
  const navigate = useNavigate();

  const [book, setBook] = useState<BookDetail | null>(null);
  const [body, setBody] = useState<FullTextResponse | null>(null);
  const [housePool, setHousePool] = useState<BookSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
  }, [documentId]);

  // ── The ONE rich-render gate (Reader SPR-03 M4), §9.0-DEFENDED ────────────
  // Deserialize the SPR-02 `structured_blocks` into the SPR-01 typed `Document`
  // the one <Reader> renders — but ONLY for a SERVABLE book. What this gate
  // DEFENDS, precisely (defense-in-depth):
  //   • `book.servable_full_text` must be true (the §9.0 serve verdict) — we
  //     NEVER rich-render a gated/taken-down book, even if a stale/poisoned
  //     `structured_blocks` somehow rode along (the backend serves it null for a
  //     withheld body, but the client refuses regardless);
  //   • the JSON must PARSE, carry a `blocks` array, AND every block must have a
  //     KNOWN `type` discriminator (allBlockTypesKnown, sourced from the
  //     generated `Block` union). A bad/wrong-shape blob — unparseable, no
  //     `blocks` array, or a block whose `type` the dispatcher can't render
  //     (`assertNever`) — degrades to null, taking the legacy text fallback
  //     BEFORE the renderer can throw on it.
  // This gate validates SHAPE only (parse + a known-`type` block array); it does
  // NOT deep-validate every span/field, so a field-level skew within a known
  // type (a `paragraph` missing `spans`, a `math` missing `tex`) can still slip
  // through to render — that residual is caught by the ReaderErrorBoundary
  // around the rich body, which degrades to the SAME legacy fallback. Together:
  // never a blank, never a throw.
  // A null result ⇒ the legacy `ReadingColumn` text path, byte-identical to
  // before. So the rich path is reachable for a servable, well-formed doc ONLY.
  const structuredDoc = useMemo<Document | null>(() => {
    if (!book?.servable_full_text || !body?.structured_blocks) return null;
    try {
      const d = JSON.parse(body.structured_blocks);
      if (!d || !Array.isArray(d.blocks)) return null;
      // Reject a doc carrying any unknown block `type` (schema-skew / poisoned)
      // BEFORE it reaches the dispatcher's `assertNever` — take the clean
      // legacy fallback instead of letting the renderer throw.
      if (!allBlockTypesKnown(d.blocks)) return null;
      return d as Document;
    } catch {
      return null;
    }
  }, [book?.servable_full_text, body?.structured_blocks]);

  // ── ONE active pagination both paths reconcile to (M4) ───────────────────
  // The RISK this closes: the page COUNT the pager / usePosition / ad-impression
  // slots key off MUST equal the rendered page count, or impressions misfire.
  // We compute BOTH paginations but expose a SINGLE normalized `pages` array of
  // `{pageNumber}` — its `.length` IS the rendered page count on whichever path
  // is active, so every consumer (usePosition, the observePage effect, the
  // pager, ad slots) reads the SAME count. The body-render branch below selects
  // which content each page shows; this array selects HOW MANY pages exist.
  //   • structuredDoc present → block windows (paginateBlocks): one window per
  //     ≤12-block page; an empty doc → exactly one window (chrome still renders).
  //   • structuredDoc null    → text windows (paginate over full_text/snippet).
  // Both honour the "always ≥1 window for any served body, 0 for none" contract
  // the ad-impression effect already relies on.
  const blockWindows = useMemo(
    () => (structuredDoc ? paginateBlocks(structuredDoc.blocks ?? []) : []),
    [structuredDoc],
  );
  const textPages = useMemo(
    () => paginate(body?.full_text ?? body?.snippet ?? ""),
    [body],
  );
  // The ONE active pagination. On the rich path the block windows drive the
  // count; on the legacy path the text windows do. `pageNumber` is the only
  // field every consumer needs from the normalized array.
  const pages = useMemo<{ pageNumber: number }[]>(
    () =>
      structuredDoc
        ? blockWindows.map((w) => ({ pageNumber: w.pageNumber }))
        : textPages.map((p) => ({ pageNumber: p.pageNumber })),
    [structuredDoc, blockWindows, textPages],
  );
  const { pageIndex, setPageIndex } = usePosition(documentId, pages.length);

  // Citation → page jump (M2). A talk-to-book / search citation carries a
  // resolved 0-based page; clamp it onto the active pagination and move the
  // reader via the SAME setPageIndex the pager and TOC jumps use — not a
  // parallel path. The citation's page index is a position over the SAME
  // normalized `pages`, so clamping over its length is correct on either active
  // pagination (block windows or text windows).
  const jumpToPage = useCallback(
    (page: number) => {
      // Clamp the 0-based page into [0, length-1] inline over the active
      // normalized `pages` (whichever path is active) — same semantics on both.
      if (pages.length === 0) return;
      setPageIndex(Math.max(0, Math.min(page, pages.length - 1)));
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
  // source.read history, and the rabbit-hole's parent together — they all
  // read/append to the same thread. Not a user-facing label (copy-lint): it is
  // passed to components, never rendered.
  const readingThreadId = `read-${documentId}`;

  // §9.0 — the chunk the read/note is attributed to.
  //
  // HONEST GAP (Read SPR-07 M4, tightened): the reader client has NO chunk id
  // to attribute to this sprint. BookDetail / FullTextResponse expose
  // title/toc/full_text/servability — never per-chunk ids — and surfacing them
  // is a backend change (a /books endpoint that returns chunk ids) deliberately
  // OUT OF SCOPE here. So we attribute to null HONESTLY rather than invent a
  // chunk id. Consequence, stated plainly so the M4 claim is not overstated:
  //   • source.read EVENT + the SiteSee resolver are LIVE (sourceRead.ts);
  //   • the SiteSee "read" tint keys on chunk_id, so it PAINTS only once a
  //     real chunk anchor is resolved — a documented follow-up (a books
  //     endpoint exposing chunk ids), NOT something this sprint claims paints
  //     end-to-end.
  // For the in-book NOTE: document_id still completes the claim→chunk→document
  // chain (the note's per-book insight node is grounded on its document via
  // node metadata, so block_search returns it per-book even with a null chunk —
  // see substrate/graph/insight_question.promote_from_marginalia_event). The
  // chunk anchor on the note is the SAME documented follow-up.
  const representativeChunkId: string | null = null;

  // source.read (SPR-07 M4) — fire ONCE per source per reading session on the
  // justified dwell threshold, reusing the focused-dwell clock the ad-impression
  // tracker already runs. A per-session guard (ref) coalesces it: never per-page
  // spam, never refired. §9.0: the event carries no body (sourceRead.ts).
  const readEmittedRef = useRef(false);
  const onDwell = useCallback(
    (dwell: { totalDwellMs: number; pagesSeen: number }) => {
      if (readEmittedRef.current) return;
      if (!isRead(dwell.totalDwellMs, dwell.pagesSeen)) return;
      readEmittedRef.current = true;
      void emitSourceRead({
        documentId,
        readingThreadId,
        chunkId: representativeChunkId,
        dwellMs: dwell.totalDwellMs,
        pageCount: dwell.pagesSeen,
      });
    },
    [documentId, readingThreadId],
  );
  const { observePage } = useReaderImpressions(documentId, sessionId, onDwell);
  const [showVoice, setShowVoice] = useState(false);
  // ── M5 view-original toggle ───────────────────────────────────────────────
  // The structured model is the DEFAULT view. When a preserved original (a PDF
  // blob) exists, a toggle reveals it via PdfViewer as a SECONDARY view; with no
  // original the toggle is hidden entirely (no dead control). Reset to the
  // structured default whenever the open document changes.
  const [showOriginal, setShowOriginal] = useState(false);
  useEffect(() => {
    setShowOriginal(false);
  }, [documentId]);

  // ── In-book SPR-04 float-menu host (SPR-07 M2) ───────────────────────────
  // The reader is the HOST for the SAME shared FloatMenu Research uses — it is
  // REUSED, not re-implemented (verify by import: ../shared/FloatMenu/FloatMenu).
  // The page <article> is the selection SCOPE; `resolveProvenance` resolves the
  // book selection's document + its §9.0 servable flag so the menu's outbound
  // chokepoint can refuse a withheld selection. The in-book highlight→action
  // (the old inline "Go deeper" affordance) is GENERALIZED through this menu —
  // Deep-research routes to the SAME ChaseThread the rabbit-hole used, so there
  // is ONE in-book highlight primitive, consistent with the Research surface.
  const articleRef = useRef<HTMLElement>(null);

  // `chasing` is the passage currently being chased (mounts ChaseThread inline
  // beside the reading column, text + voice). The way home is free: closing the
  // chase restores reading, and usePosition has held the page the whole time.
  const [chasing, setChasing] = useState<string | null>(null);

  // §9.0 servability of the open book — the in-book selection's servability.
  // The reader renders only gate-served body (verified: getBookFullText returns
  // full_text:null for a gated/taken-down book), so `book.servable_full_text`
  // IS the selection's servable flag: a selection can only be from text the gate
  // served. We pass it through so the FloatMenu chokepoint refuses Search/Deep-
  // research over a non-servable book (defence in depth — the body can't even
  // reach the DOM, but the outbound guard holds regardless).
  const resolveProvenance = useCallback(
    (_range: Range, _text: string): SelectionProvenance => ({
      documentId,
      chunkId: representativeChunkId,
      servable: book?.servable_full_text ?? false,
    }),
    [documentId, book?.servable_full_text],
  );

  const selection = useFloatMenuSelection({
    scopeRef: articleRef,
    resolveProvenance,
    minLength: 8,
  });

  // Deep-research → the EXISTING in-book chase (ChaseThread mounts inline
  // beside the reading column, the same path the old "Go deeper" affordance
  // used). §9.0: `safeSpawnText` is null when the selection crosses a withheld
  // region — refuse rather than spawn on a withheld body (the chokepoint already
  // refuses, so this is null only for a non-servable book; we never chase it).
  const onDeepResearch = useCallback(
    (safeSpawnText: string | null, _sel: FloatMenuSelection) => {
      if (safeSpawnText === null) return;
      window.getSelection()?.removeAllRanges(); // collapse so the menu closes
      setChasing(safeSpawnText);
    },
    [],
  );

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
    return <CenterNote>Opening the book…</CenterNote>;
  }
  if (error || !book || !body) {
    return (
      <CenterNote tone="error">
        {error === "book_not_found" ? "That book isn't in the library." : error}
      </CenterNote>
    );
  }

  const { label, colour } = servabilityLabel(book.servability);
  // The active page over the NORMALIZED pagination (carries `pageNumber` for the
  // pager). On the rich path `activeWindow` carries the page's blocks; on the
  // legacy path `textPage` carries the page's markdown — exactly one is used by
  // the body branch below, but both index into a pagination of the SAME length
  // as `pages`, so the pager/ad-slot count never disagrees with what renders.
  const page = pages[pageIndex];
  const activeWindow = structuredDoc ? blockWindows[pageIndex] : undefined;
  const textPage = structuredDoc ? undefined : textPages[pageIndex];
  // The current page's plain passage text — the seed for ResearchThis / spin-
  // research. On the rich path it is flattened from the window's blocks; on the
  // legacy path it is the page markdown. Either way it is the SAME gate-served
  // body for this page (a gated book never reaches the body branch with text).
  const activePassageText = structuredDoc
    ? blocksToPlainText(activeWindow?.blocks ?? [])
    : (textPage?.text ?? "");
  // D1 degrade text: if the rich <Reader> throws on a field-level skew the
  // structuredDoc gate didn't catch (a paragraph missing `spans`, a math missing
  // `tex`), the error boundary degrades to the legacy ReadingColumn with this
  // text. The block pagination and the text pagination don't share page indices,
  // so a mid-doc throw can't be mapped to a single text page reliably; the honest
  // degrade renders the WHOLE gate-served body (same §9.0-served text) rather
  // than a mis-mapped page. Empty body ⇒ ReadingColumn shows its honest
  // "no readable pages" notice — still not blank, still no throw.
  const legacyFallbackText = body.full_text ?? body.snippet ?? "";
  // M5: the preserved-original PDF bytes, or null when no original exists. Books
  // persist raw_text as the "view original" source (SPR-02 store-both), NOT a
  // PDF blob, and no endpoint serves PDF bytes for a book — so this is null for
  // every current book and the toggle stays hidden. The seam is wired for a
  // future PDF-bytes source without fabricating bytes that don't exist.
  //
  // M5 seam wired; structurally hidden until a PDF-bytes source exists — no
  // `documents` PDF-blob column today. The toggle-hidden state is verified by a
  // test ("M5: the view-original toggle is HIDDEN when there is no original").
  const originalPdfBytes: Uint8Array | null = null;
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

  // ── ToC reconciliation (M4) ──────────────────────────────────────────────
  // On the RICH path the ToC is DERIVED from the document's heading blocks
  // (deriveToc) and each entry's jump target is the BLOCK window that contains
  // it (windowForBlockIndex) — so a heading scrolls to its actual page over the
  // SAME block pagination the body renders. On the LEGACY path it stays the
  // backend `book.toc` (TocItem with a resolved page_index over the text
  // pagination), unchanged. Both feed the ONE TocPanel as TocItem[] whose
  // `page_index` is a window index over the ACTIVE pagination, so a TOC jump and
  // the rendered page never disagree on either path.
  const activeToc: TocItem[] = structuredDoc
    ? (deriveToc(structuredDoc.blocks ?? []) as TocEntry[]).map((e) => ({
        title: e.text,
        page_index: windowForBlockIndex(blockWindows, e.block_index),
        level: Math.max(0, e.level - 1),
      }))
    : book.toc;

  return (
    <div className="flex h-screen bg-ice-0 dark:bg-charcoal-2">
      {/* TOC sidebar */}
      <aside className="w-64 flex-shrink-0 border-r border-rule dark:border-charcoal-1 overflow-y-auto p-3 hidden md:block">
        <p className="font-serif text-sm text-ink dark:text-bright mb-1 truncate">
          {book.title ?? documentId}
        </p>
        <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight mb-3 truncate">
          {book.author ?? "Unknown author"}
        </p>
        <TocPanel toc={activeToc} currentPageIndex={pageIndex} onJump={setPageIndex} />
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
          a model-emerged insight. Deep-research routes to ChaseThread (below).
          Hidden while a chase owns the column. §9.0: the outbound chokepoint
          refuses Search/Deep-research over a non-servable book. */}
      {!chasing && (
        <FloatMenu
          selection={selection}
          investigationId={readingThreadId}
          onDeepResearch={onDeepResearch}
        />
      )}

      {/* Reading column */}
      <main className="flex-1 overflow-y-auto">
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
              className="text-[13px] border-edge border-sun rounded-md bg-sun/15 px-3 py-2 text-ink dark:text-bright"
            >
              This paper is read on arXiv, but its arXiv link isn’t available
              right now. Try again later or search arXiv for the title above.
            </div>
          ) : (
            <>
              {!book.servable_full_text && (
                <div className="text-[13px] border-edge border-sun rounded-md bg-sun/15 px-3 py-2 text-ink dark:text-bright">
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
              {/* M5 view-original toggle — only when a preserved ORIGINAL exists.
                  The structured model is the DEFAULT; the original is a SECONDARY
                  view. No original (originalPdfBytes null) ⇒ no toggle (no dead
                  control). Per the SPR-02 store-both decision, a book's preserved
                  original is its raw_text markdown — no PDF blob is persisted for
                  books and no endpoint serves one — so originalPdfBytes is null
                  for every current book and the toggle is hidden. The seam is
                  here, correctly wired, for when a PDF-bytes source lands. */}
              {originalPdfBytes && (
                <div className="flex items-center justify-end">
                  <LemonButton
                    type="button"
                    variant="tertiary"
                    size="sm"
                    aria-pressed={showOriginal}
                    onClick={() => setShowOriginal((v) => !v)}
                  >
                    {showOriginal ? "Back to reading view" : "View original"}
                  </LemonButton>
                </div>
              )}

              {originalPdfBytes && showOriginal ? (
                /* SECONDARY view: the preserved original via the ONE PdfViewer.
                    The structured model stays the default; this is only reached
                    when an original exists AND the reader explicitly toggled. */
                <div className="h-[70vh] overflow-hidden border border-rule dark:border-charcoal-1 rounded-md">
                  <PdfViewer
                    pdfBytes={originalPdfBytes}
                    investigationId={readingThreadId}
                    documentId={documentId}
                  />
                </div>
              ) : structuredDoc ? (
                /* RICH path (DEFAULT): the one <Reader> renders the typed-block
                    Document for the current page window. PRESERVES verbatim: the
                    articleRef (FloatMenu selection scope), the SPR-07 attribution
                    markers (Reader stamps data-akb-asset-id from a truthy assetId
                    — present here ONLY for a servable book, §9.0), and no
                    fabricated chunkId. openDocument is the SPR-03 stub (SPR-05
                    wires the real gated resolver).

                    D1 — "never blank, never a throw": the structuredDoc gate
                    rejects an unknown block `type` up front, but a field-level
                    skew within a KNOWN type (a paragraph missing `spans`, a math
                    missing `tex`) would still throw during render. With no
                    boundary that throw unmounts the whole surface to blank. The
                    ReaderErrorBoundary catches it and degrades to the SAME legacy
                    ReadingColumn — same articleRef, same §9.0 attribution — that
                    a null structuredDoc takes. resetKey=documentId lets a healthy
                    book after a broken one render rich again. */
                <ReaderErrorBoundary
                  resetKey={documentId}
                  fallback={
                    <ReadingColumn
                      ref={articleRef}
                      assetId={book.servable_full_text ? documentId : null}
                      text={legacyFallbackText}
                    />
                  }
                >
                  <Reader
                    ref={articleRef}
                    document={structuredDoc}
                    blocks={activeWindow?.blocks ?? []}
                    assetId={book.servable_full_text ? documentId : null}
                    chunkId={null}
                    openDocument={openDocumentStub}
                  />
                </ReaderErrorBoundary>
              ) : (
                /* LEGACY path: a null structuredDoc (un-backfilled / bad-JSON /
                    gated snippet) renders the markdown ReadingColumn flattener —
                    byte-identical to before. Same articleRef + same §9.0 assetId
                    gate. Additive, never a blank. */
                <ReadingColumn
                  ref={articleRef}
                  assetId={book.servable_full_text ? documentId : null}
                  text={textPage?.text ?? ""}
                />
              )}

              {/* Per-page actions: voice note + spin a deep research. Hidden in
                  the view-original secondary view (the original owns the column).
                  passageText comes from the ACTIVE page on whichever path: the
                  rich path lifts the window's plain text, the legacy path the
                  markdown — both are the gate-served body for this page. */}
              {page && !(originalPdfBytes && showOriginal) && (
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
                    <ResearchThis documentId={documentId} pageIndex={pageIndex} passageText={activePassageText} />
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
              <span className="text-[12px] font-mono text-shadow-1 dark:text-moonlight">
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

      {/* The Read glass-box (M2) + the inline rabbit-hole answer (M3) share
          the right column. While a passage is being chased, the column IS the
          inline chase — the answer lands right beside the reading column,
          text or voice (ChaseThread carries VoiceChaseButton). Otherwise it is
          the reading companion. Closing the chase returns to the companion;
          the page never moved (usePosition), so reading resumes where it was —
          a reversible seam, not a one-way trip. */}
      {chasing ? (
        <aside
          className="w-80 flex-shrink-0 border-l border-rule dark:border-charcoal-1 overflow-y-auto bg-ice-1 dark:bg-charcoal-2 hidden lg:flex lg:flex-col"
          aria-label="Following this passage"
        >
          <div className="flex items-center justify-between px-3 py-2 border-b border-rule dark:border-charcoal-1">
            <span className="text-[11px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
              Following a passage
            </span>
            <button
              type="button"
              onClick={() => setChasing(null)}
              className="text-[12px] font-mono text-ink dark:text-bright hover:underline"
              title="Close and return to reading where you left off"
            >
              ← back to the book
            </button>
          </div>
          <div className="flex-1 min-h-0">
            {/* Reuse SPR-04's chase verbatim: one launch path, the reserved-id
                discipline, the live thinking stream, honest no-key via
                AIActionFailure, and voice via VoiceChaseButton — all inherited.
                The passage is the seed; the book's reading thread is the
                parent. §9.0: the reader only ever rendered gate-served text,
                so a highlight can only carry what the gate already permitted. */}
            <ChaseThread
              spawnContext={chasing}
              parentInvestigationId={readingThreadId}
            />
          </div>
        </aside>
      ) : (
        <ReadingCompanion
          documentId={documentId}
          title={book.title}
          readingThreadId={readingThreadId}
        />
      )}

      {/* M2 — the floating bookmark: a book-level MULTI-TURN talk-to-book
          conversation that persists across page navigation (session state, the
          usePosition precedent). Answers cite pages → jumpToPage moves the
          SPR-07 reader. The SPR-04 selection FloatMenu Dialogue stays one-shot;
          THIS is the new multi-turn surface. */}
      <TalkToBook documentId={documentId} title={book.title} onJumpToPage={jumpToPage} />
    </div>
  );
}

/**
 * Flatten a page window's blocks to plain text — the spin-research / ResearchThis
 * seed for the rich path. Mirrors the Reader's `_spans_to_plain_text` register
 * (a citation contributes its marker, math its tex), so the seed reads as the
 * passage the reader sees. Only the block kinds that carry readable inline text
 * contribute; structural-only kinds (figure src, code fence language) are
 * skipped. The whole window is joined with newlines so multi-paragraph pages
 * seed coherently.
 */
function blocksToPlainText(blocks: Block[]): string {
  const out: string[] = [];
  const spanText = (spans: InlineSpan[] | undefined): string => {
    if (!spans) return "";
    const parts: string[] = [];
    for (const span of spans) {
      switch (span.type) {
        case "text":
        case "code":
          parts.push(span.text);
          break;
        case "math":
          parts.push(span.tex);
          break;
        case "citation":
          parts.push(span.marker);
          break;
        case "strong":
        case "emphasis":
        case "link":
          parts.push(spanText(span.children));
          break;
      }
    }
    return parts.join("");
  };
  const walk = (bs: Block[]): void => {
    for (const b of bs) {
      switch (b.type) {
        case "heading":
        case "paragraph":
          out.push(spanText(b.spans));
          break;
        case "code":
          out.push(b.text);
          break;
        case "list":
          for (const item of b.items) walk(item.blocks);
          break;
        case "blockquote":
        case "footnote":
          walk(b.blocks);
          break;
        case "figure":
          if (b.caption) out.push(spanText(b.caption));
          break;
        // math (display) / table contribute no linear passage text for the seed.
      }
    }
  };
  walk(blocks);
  return out.filter(Boolean).join("\n").trim();
}

function CenterNote({ children, tone }: { children: React.ReactNode; tone?: "error" }) {
  return (
    <div className="h-screen flex items-center justify-center bg-ice-0 dark:bg-charcoal-2">
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
