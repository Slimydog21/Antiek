import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { BookSummary, CorpusStatus } from "../../api/books";
import { curateBooks, listBooks } from "../../api/books";
import { listInvestigations } from "../../lib/api";
import type { InvestigationSummary } from "../../lib/api";
import { useInWindow } from "../../components/windows/windowHostContext";
import GlassSurface from "../../shell/GlassSurface";
import BookCard from "./BookCard";
import CorpusSearch from "./CorpusSearch";
import CuratePrompt from "./CuratePrompt";
import { documentsByTheme } from "./documentsByTheme";
import type { FeedOrdering } from "./documentsByTheme";
import WernerIceHole from "./WernerIceHole";

/**
 * Library — the home of the Read workflow (Read SPR-02; re-homed as the Read
 * DOOR in Read SPR-06).
 *
 * A shelf/grid over the servable corpus. The legal posture is visible in
 * the IA, not just the backend: the default view is the servable shelf
 * (public-domain + Antiek originals + publisher-licensed), and gated
 * books appear only under "Preview" — flagged, never implying full-text
 * access. This is Spotify-for-books: a licensed shelf, not an aggregator.
 *
 * Opening a book routes to /read/:documentId (SPR-03), which renders only
 * what the serve gate permits.
 *
 * Read SPR-06: this is the Read workflow's defaultRoute (the door). The PDF
 * wrestler is demoted from the door to a "bring your own PDF" affordance
 * here — still reachable for the power case, no longer the home. An empty
 * shelf shows an honest "what's available to read" state, NOT an uploader.
 */

const FILTERS: { key: CorpusStatus; label: string; hint: string }[] = [
  { key: "servable", label: "Shelf", hint: "Readable in full" },
  { key: "gated", label: "Preview", hint: "Metadata + snippet only" },
  { key: "all", label: "All", hint: "Everything, flagged" },
];

export default function Library() {
  const navigate = useNavigate();
  // SPR-09 window-adaptation contract: in a WorkspaceWindow, fill the
  // container (h-full) and drop the opaque full-bleed bg so the glass shows
  // through. Gated on this flag → the full-page route is unchanged.
  const inWindow = useInWindow();
  const [status, setStatus] = useState<CorpusStatus>("servable");
  const [books, setBooks] = useState<BookSummary[]>([]);
  // Active research, the signal documentsByTheme ranks the shelf to (M1).
  // Best-effort: a failed/empty fetch falls the feed back to recency, honestly.
  const [investigations, setInvestigations] = useState<InvestigationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Prompt-to-curate (SPR-04): an ordered list of servable document_ids,
  // or null when no prompt is active. Curated books are a re-ranked subset
  // of the servable shelf.
  const [curatedOrder, setCuratedOrder] = useState<string[] | null>(null);
  const [curatePrompt, setCuratePrompt] = useState<string>("");
  const [curateBusy, setCurateBusy] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listBooks(status);
      setBooks(data.books);
      // Pull active research themes only for the default servable shelf — the
      // theme-ranked feed is the Read DOOR's first view. Best-effort: if the
      // research list is unavailable, the feed falls back to recency (the empty
      // investigations set → documentsByTheme returns ordering "recency").
      if (status === "servable") {
        try {
          const inv = await listInvestigations({ status: "in_progress" });
          setInvestigations(inv.investigations);
        } catch {
          setInvestigations([]); // thin signal → recency fallback, honestly
        }
      } else {
        setInvestigations([]);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    void reload();
    // Switching shelves clears any active curation.
    setCuratedOrder(null);
    setCuratePrompt("");
  }, [reload]);

  const onCurate = useCallback(async (prompt: string) => {
    setCurateBusy(true);
    setError(null);
    try {
      const res = await curateBooks(prompt);
      setCuratedOrder(res.books.map((b) => b.document_id));
      setCuratePrompt(prompt);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCurateBusy(false);
    }
  }, []);

  const onClearCurate = useCallback(() => {
    setCuratedOrder(null);
    setCuratePrompt("");
  }, []);

  // The display order, in three layers of precedence:
  //   1. an ACTIVE CURATE prompt (explicit user query) re-ranks to that order;
  //   2. otherwise, on the default servable shelf, documentsByTheme ranks to
  //      the user's active research themes (M1) — or falls back to recency with
  //      a STATED label when the theme signal is thin (the honesty seam);
  //   3. on the Preview / All shelves there is no ambient theme ranking — they
  //      are flagged catalogues, shown in their given (recency) order.
  // `ordering`/`themeTerms` drive the honest label the surface renders.
  const { displayed, ordering, themeTerms } = useMemo<{
    displayed: BookSummary[];
    ordering: FeedOrdering | null;
    themeTerms: string[];
  }>(() => {
    if (curatedOrder) {
      // Curated: re-rank the loaded shelf to the curated order; books not in
      // the shelf (shouldn't happen — curate is servable-only) are dropped
      // rather than rendered without their metadata.
      const byId = new Map(books.map((b) => [b.document_id, b]));
      const curated = curatedOrder
        .map((id) => byId.get(id))
        .filter((b): b is BookSummary => Boolean(b));
      return { displayed: curated, ordering: null, themeTerms: [] };
    }
    if (status === "servable") {
      const feed = documentsByTheme(books, investigations);
      return { displayed: feed.books, ordering: feed.ordering, themeTerms: feed.themeTerms };
    }
    return { displayed: books, ordering: null, themeTerms: [] };
  }, [curatedOrder, books, status, investigations]);

  const open = useCallback(
    (documentId: string) => navigate(`/read/${encodeURIComponent(documentId)}`),
    [navigate],
  );

  // Open a book at a specific page (M1 search-result jump). The reader reads its
  // page from the SAME sessionStorage locator usePosition owns (no new
  // mechanism); seeding it here lands the reader on the cited page. A null /
  // unresolved page opens at the saved position (honest — no fake page jump).
  const openAtPage = useCallback(
    (documentId: string, pageIndex?: number | null) => {
      if (pageIndex !== null && pageIndex !== undefined && pageIndex >= 0) {
        try {
          window.sessionStorage.setItem(`antiek.read.pos.${documentId}`, String(pageIndex));
        } catch {
          /* private mode — the reader still opens, just at the saved page */
        }
      }
      navigate(`/read/${encodeURIComponent(documentId)}`);
    },
    [navigate],
  );

  const subtitle = useMemo(() => {
    if (loading) return "Loading the shelf…";
    if (status === "servable") return `${books.length} books readable in full`;
    if (status === "gated") return `${books.length} preview-only titles`;
    return `${books.length} titles`;
  }, [loading, status, books.length]);

  // The Library shelf body. Two surfaces:
  //  - inWindow (SPR-09 contract): a WorkspaceWindow already owns the glass, so
  //    the body stays bg-transparent and is NOT re-glassed — preserved verbatim.
  //  - the full-page landing (the Read door): a LANDING surface (SPR-03 M2) —
  //    its body renders through GlassSurface so the <Scene/> (z-0) shows through
  //    instead of the old opaque bg-ice-0 dark:bg-charcoal-2 wall; the scrim
  //    keeps the shelf header + body text legible (WCAG-AA owned by the glass).
  const shelfBody = (
    <div className="max-w-5xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <div className="flex items-start justify-between gap-4">
              <h1 className="text-2xl font-serif text-ink dark:text-bright">Library</h1>
              <div className="shrink-0 mt-1 flex items-center gap-4">
                {/* SPR-09 M2: the paginated browse view over the catalog endpoint
                    — for scanning the whole shelf a page at a time. Additive to
                    the theme-ranked door. */}
                <button
                  type="button"
                  onClick={() => navigate("/library/browse")}
                  className="text-xs font-mono text-shadow-1 dark:text-moonlight underline decoration-dotted underline-offset-2 hover:text-ink dark:hover:text-bright"
                  title="Browse the whole catalog, a page at a time"
                >
                  browse all →
                </button>
                {/* Read SPR-06: the PDF wrestler, demoted from the Read door to a
                    bring-your-own affordance. Reachable for the power case (read a
                    PDF you brought), no longer the home — the shelf is. */}
                <button
                  type="button"
                  onClick={() => navigate("/wrestle")}
                  className="text-xs font-mono text-shadow-1 dark:text-moonlight underline decoration-dotted underline-offset-2 hover:text-ink dark:hover:text-bright"
                  title="Read a PDF you bring yourself"
                >
                  bring your own PDF →
                </button>
              </div>
            </div>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              A licensed shelf of what can be aggregated — public-domain works,
              Antiek originals, and publisher-opted-in titles you can read in
              full. A library, not a marketplace: everything else is
              preview-only. {subtitle}.
            </p>
          </header>

          <WernerIceHole />

          <div
            role="tablist"
            aria-label="Corpus filter"
            className="flex items-center gap-2"
          >
            {FILTERS.map((f) => (
              <button
                key={f.key}
                role="tab"
                aria-selected={status === f.key}
                type="button"
                title={f.hint}
                onClick={() => setStatus(f.key)}
                className={`px-3 py-1 rounded-md text-xs font-mono transition-colors ${
                  status === f.key
                    ? "bg-ink text-white"
                    : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright hover:bg-ice-4"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* M1: search the OWNED corpus — typed query OR file-drop bias.
              Theme-context (the active research themes) is folded into the
              query when present, degrading gracefully when absent. */}
          <CorpusSearch onOpen={openAtPage} themeContext={themeTerms} />

          {/* M4: meta-reading entry — deep-research the owned corpus into a
              re-openable, length-boxed Read asset. PROPOSED boundary (sign-off
              pending) — the surface itself carries the banner. */}
          <div className="flex items-center justify-between gap-3 rounded-md border border-sun/40 bg-sun/10 px-3 py-2">
            <p className="text-[13px] font-serif text-ink dark:text-bright">
              Make a reading asset from your corpus
              <span className="ml-2 text-[11px] font-mono uppercase tracking-wider text-sun-deep dark:text-sun">
                proposed
              </span>
            </p>
            <button
              type="button"
              onClick={() => navigate("/read/meta-reading")}
              className="shrink-0 text-xs font-mono text-ink dark:text-bright underline decoration-dotted underline-offset-2 hover:opacity-80"
            >
              Meta-read →
            </button>
          </div>

          {status === "servable" && (
            <CuratePrompt
              onCurate={onCurate}
              onClear={onClearCurate}
              active={curatedOrder !== null}
              busy={curateBusy}
            />
          )}

          {curatedOrder !== null && (
            <p className="text-[13px] font-serif text-ink dark:text-bright">
              Curated for “<span className="italic">{curatePrompt}</span>” —{" "}
              {displayed.length} {displayed.length === 1 ? "book" : "books"}, best match first.
            </p>
          )}

          {/* M1 honesty seam: SAY which ordering is active. A theme-ranked feed
              names the research it ranked to; a thin-signal fallback admits it
              is showing recency, never dressing it up as relevance. Only on the
              default servable shelf, and never while a curate prompt overrides. */}
          {curatedOrder === null && !loading && displayed.length > 0 && ordering === "theme" && (
            <p className="text-[13px] font-serif text-ink dark:text-bright" data-feed-ordering="theme">
              Ranked to your active research
              {themeTerms.length > 0 && (
                <>
                  {" — "}
                  <span className="italic">{themeTerms.slice(0, 4).join(", ")}</span>
                </>
              )}
              .
            </p>
          )}
          {curatedOrder === null && !loading && displayed.length > 0 && ordering === "recency" && (
            <p className="text-[13px] font-serif text-shadow-1 dark:text-moonlight" data-feed-ordering="recency">
              No active research to rank to yet — showing the most recently added first.
            </p>
          )}

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
          )}

          {!loading && !error && displayed.length === 0 && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">
              {curatedOrder !== null
                ? "No servable books matched that prompt. Try different words, or clear to see the whole shelf."
                : status === "servable"
                  ? "Nothing is readable in full on the shelf yet — the library only shows what can be legally aggregated. Check the Preview tab for titles you can sample, or bring your own PDF to read it here."
                  : "Nothing here."}
            </p>
          )}

          {displayed.length > 0 && (
            <section
              aria-label="Books"
              className="grid gap-5"
              style={{ gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))" }}
            >
              {displayed.map((b) => (
                <BookCard key={b.document_id} book={b} onOpen={open} />
              ))}
            </section>
          )}
    </div>
  );

  return (
    <div className={`flex flex-col ${inWindow ? "h-full" : "h-screen"}`}>
      {inWindow ? (
        // SPR-09 contract preserved: the host WorkspaceWindow owns the glass;
        // the body stays bg-transparent and is NOT re-glassed.
        <main className="flex-1 overflow-y-auto bg-transparent">{shelfBody}</main>
      ) : (
        // Full-page Read door landing → glass over the living scene.
        <GlassSurface as="main" className="flex-1 overflow-y-auto">
          {shelfBody}
        </GlassSurface>
      )}
    </div>
  );
}
