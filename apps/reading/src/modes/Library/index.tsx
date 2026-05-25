import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { BookSummary, CorpusStatus } from "../../api/books";
import { curateBooks, listBooks } from "../../api/books";
import BookCard from "./BookCard";
import CuratePrompt from "./CuratePrompt";

/**
 * Library — the home of the Read workflow (Read SPR-02).
 *
 * A shelf/grid over the servable corpus. The legal posture is visible in
 * the IA, not just the backend: the default view is the servable shelf
 * (public-domain + Antiek originals + publisher-licensed), and gated
 * books appear only under "Preview" — flagged, never implying full-text
 * access. This is Spotify-for-books: a licensed shelf, not an aggregator.
 *
 * Opening a book routes to /read/:documentId (SPR-03), which renders only
 * what the serve gate permits.
 */

const FILTERS: { key: CorpusStatus; label: string; hint: string }[] = [
  { key: "servable", label: "Shelf", hint: "Readable in full" },
  { key: "gated", label: "Preview", hint: "Metadata + snippet only" },
  { key: "all", label: "All", hint: "Everything, flagged" },
];

export default function Library() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<CorpusStatus>("servable");
  const [books, setBooks] = useState<BookSummary[]>([]);
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

  // Curated view re-ranks the loaded servable shelf to the curated order;
  // books not present in the shelf (shouldn't happen — curate is servable-
  // only) are dropped rather than rendered without their metadata.
  const displayed = useMemo<BookSummary[]>(() => {
    if (!curatedOrder) return books;
    const byId = new Map(books.map((b) => [b.document_id, b]));
    return curatedOrder.map((id) => byId.get(id)).filter((b): b is BookSummary => Boolean(b));
  }, [curatedOrder, books]);

  const open = useCallback(
    (documentId: string) => navigate(`/read/${encodeURIComponent(documentId)}`),
    [navigate],
  );

  const subtitle = useMemo(() => {
    if (loading) return "Loading the shelf…";
    if (status === "servable") return `${books.length} books readable in full`;
    if (status === "gated") return `${books.length} preview-only titles`;
    return `${books.length} titles`;
  }, [loading, status, books.length]);

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-5xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-ink dark:text-bright">Library</h1>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              A licensed shelf — public-domain works, Antiek originals, and
              publisher-opted-in titles you can read in full. Everything else
              is preview-only. {subtitle}.
            </p>
          </header>

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
                  ? "No servable books yet. Ingest a public-domain title or an Antiek original to start the shelf."
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
      </main>
    </div>
  );
}
