import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { LemonButton, LemonTag } from "../../components/lemon";
import type { BookDetail, BookSummary, FullTextResponse } from "../../api/books";
import { getBook, getBookFullText, listBooks, servabilityLabel } from "../../api/books";
import { getChunk } from "../../lib/api";
import AdBorder from "./AdBorder";
import type { AdFillView } from "./AdBorder";
import { findPageForChunkText } from "./anchorToChunk";
import ResearchThis from "./ResearchThis";
import TocPanel from "./TocPanel";
import VoiceNote from "./VoiceNote";
import { paginate } from "./paginate";
import { usePosition } from "./usePosition";
import { useReaderImpressions } from "./useReaderImpressions";

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

  // Chunk-span anchor: when opened with ``?chunk=<chunk_id>`` (e.g. from a
  // Write trace-to-source), resolve the chunk to its text and jump to the
  // page that contains it — landing on the EXACT cited span, not just the
  // document. Best-effort: a chunk that doesn't resolve or isn't located
  // leaves the saved position untouched (never throws, never misleads).
  const [searchParams] = useSearchParams();
  const chunkAnchor = searchParams.get("chunk");
  useEffect(() => {
    if (!chunkAnchor || pages.length === 0) return;
    let cancelled = false;
    (async () => {
      try {
        const chunk = await getChunk(chunkAnchor);
        if (cancelled || !chunk.text) return;
        const target = findPageForChunkText(pages, chunk.text);
        if (target >= 0) setPageIndex(target);
      } catch {
        /* anchor is best-effort; fall back to the saved position */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chunkAnchor, pages, setPageIndex]);

  // Reader ad-impression flushing (SPR-05). A stable session id per mount;
  // the hook tracks focused dwell and flushes the page's slots on change.
  const [sessionId] = useState(
    () =>
      "rs-" +
      (typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID().replace(/-/g, "").slice(0, 12)
        : Math.random().toString(36).slice(2, 14)),
  );
  const { observePage } = useReaderImpressions(documentId, sessionId);
  const [showVoice, setShowVoice] = useState(false);

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

          {/* Ad-border (top) — house state by default (zero buyers). */}
          <AdBorder slotId={`${slotBase}:top`} position="top" fill={houseFill} onOpenHouse={openHouse} />

          {/* Page body */}
          <article className="flex-1 font-serif text-[15px] leading-[1.7] text-ink dark:text-bright">
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
                  investigationId={`read-${documentId}`}
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
