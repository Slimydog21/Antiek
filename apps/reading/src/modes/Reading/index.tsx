import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { LemonButton, LemonTag } from "../../components/lemon";
import type { BookDetail, BookSummary, FullTextResponse } from "../../api/books";
import { getBook, getBookFullText, listBooks, servabilityLabel } from "../../api/books";
import FloatMenu from "../shared/FloatMenu/FloatMenu";
import { useFloatMenuSelection } from "../shared/FloatMenu/useFloatMenuSelection";
import type {
  FloatMenuSelection,
  SelectionProvenance,
} from "../shared/FloatMenu/useFloatMenuSelection";
import ChaseThread from "../ResearchWorkstation/ChaseThread";
import AdBorder from "./AdBorder";
import type { AdFillView } from "./AdBorder";
import ReadingCompanion from "./ReadingCompanion";
import ResearchThis from "./ResearchThis";
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

  const pages = useMemo(
    () => paginate(body?.full_text ?? body?.snippet ?? ""),
    [body],
  );
  const { pageIndex, setPageIndex } = usePosition(documentId, pages.length);

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
    const base = `slot:${documentId}:p${pageIndex}`;
    observePage(pageIndex, [
      { slotId: `${base}:top`, fill: houseFill },
      { slotId: `${base}:bottom`, fill: houseFill },
    ]);
  }, [pageIndex, houseFill, documentId, pages.length, observePage]);

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
  const page = pages[pageIndex];
  const slotBase = `slot:${documentId}:p${pageIndex}`;

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
        <TocPanel toc={book.toc} currentPageIndex={pageIndex} onJump={setPageIndex} />
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

          {!book.servable_full_text && (
            <div className="text-[13px] border-edge border-sun rounded-md bg-sun/15 px-3 py-2 text-ink dark:text-bright">
              {book.servability === "taken_down"
                ? "This title has been removed and is no longer available to read."
                : "Preview only — this title isn’t licensed for full reading. You’re seeing a short snippet and its metadata."}
            </div>
          )}

          {/* Ad-border (top) — the v1 ad-border PLACEHOLDER (Read SPR-06 M4).
              Visual position from v1, but always the zero-buyer house fill
              here: no live ad serving, no attribution, no revenue math in this
              sprint. Real ad economics (matching, attention-weighted accrual,
              disbursement) are SPR-10 + Phase 4, gated G2/G3 — keeping them out
              here is deliberate, so a placeholder slot never implies live ads. */}
          <AdBorder slotId={`${slotBase}:top`} position="top" fill={houseFill} onOpenHouse={openHouse} />

          {/* Page body + the in-book float-menu SCOPE (M2). The shared
              useFloatMenuSelection hook listens on `selectionchange` and opens
              the menu only for selections inside this <article> — so a highlight
              anywhere in the page body offers {Note · Dialogue · Search ·
              Deep-research} by text or voice, the same primitive as Research.
              No per-element mouse/key handler: the shared hook owns the read. */}
          <article
            ref={articleRef}
            className="flex-1 font-serif text-[15px] leading-[1.7] text-ink dark:text-bright"
          >
            {page ? (
              <PageBody text={page.text} />
            ) : (
              <p className="text-shadow-1 dark:text-moonlight italic">
                This book has no readable pages.
              </p>
            )}
          </article>

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
                <ResearchThis documentId={documentId} pageIndex={pageIndex} passageText={page.text} />
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

          {/* Ad-border (bottom) */}
          <AdBorder slotId={`${slotBase}:bottom`} position="bottom" fill={houseFill} onOpenHouse={openHouse} />

          {/* Pager */}
          {pages.length > 0 && (
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
    </div>
  );
}

/** Render a page's markdown body as readable prose: `#`/`##` lines become
 * headings, blank-line-separated runs become paragraphs. Deliberately
 * light — the served body is already cleaned text, not rich markup. */
function PageBody({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
  return (
    <>
      {blocks.map((block, i) => {
        const heading = block.match(/^(#{1,3})\s+(.*)$/);
        if (heading) {
          return (
            <h2 key={i} className="font-serif font-semibold text-lg mt-4 mb-2 text-ink dark:text-bright">
              {heading[2]}
            </h2>
          );
        }
        return (
          <p key={i} className="mb-3 whitespace-pre-wrap">
            {block}
          </p>
        );
      })}
    </>
  );
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
