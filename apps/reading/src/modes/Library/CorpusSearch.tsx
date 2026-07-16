import { useCallback, useRef, useState } from "react";

import { LemonButton } from "../../components/lemon";
import { corpusSearch } from "../../api/corpusSearch";
import type { CorpusSearchHit } from "../../api/corpusSearch";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * CorpusSearch — the Library search box over the OWNED corpus (Read SPR-08 M1).
 *
 * Two ways in, ONE backend (`/corpus/search`):
 *   • a TYPED query ("looking for XYZ"); and
 *   • a FILE-DROP ("books like these") — the dropped file's text is read in the
 *     browser and used as the QUERY SIGNAL. The file is NEVER uploaded or
 *     ingested as new corpus; it biases the search instantly, no modal (the
 *     orchestrator default). We read a bounded prefix so a big file doesn't
 *     blow the query.
 *
 * When an active research THEME is present, the caller passes it as
 * `themeContext` and we fold it into the query so the search leans toward the
 * reader's current work; absent, it degrades gracefully to the raw query.
 *
 * §9.0: the backend gate excludes restricted content; this surface renders only
 * what the gate returns. A hit's page is shown only when it RESOLVED — an
 * unresolved anchor is shown honestly as "open the book", never a fake page.
 */

// Bound the dropped-file text used as the query signal — enough to characterize
// "books like these", not the whole file.
const MAX_FILE_QUERY_CHARS = 2000;

export interface CorpusSearchProps {
  /** Open a result's book in the reader (optionally at a page). */
  onOpen: (documentId: string, pageIndex?: number | null) => void;
  /** Active-research theme terms (M1 theme-context). Empty/undefined → the
   * search uses the raw query, degrading gracefully. */
  themeContext?: string[];
}

export default function CorpusSearch({ onOpen, themeContext }: CorpusSearchProps) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<CorpusSearchHit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  // The honest label for what biased this search (a dropped file vs a typed
  // query vs theme-context), so the reader knows why these results.
  const [signal, setSignal] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const run = useCallback(
    async (rawQuery: string, signalLabel: string | null) => {
      const q = rawQuery.trim();
      if (!q) {
        setHits(null);
        setSignal(null);
        return;
      }
      // Fold the active-research theme into the query when present (M1
      // theme-context); absent, the raw query stands on its own.
      const themed =
        themeContext && themeContext.length > 0
          ? `${q}\n\n(in the context of: ${themeContext.slice(0, 4).join(", ")})`
          : q;
      setBusy(true);
      setError(null);
      try {
        const res = await corpusSearch(themed);
        setHits(res.hits);
        setSignal(signalLabel);
        // Living-TV: corpus search is a curious highlight glance.
        emitWernerExperience("highlight");
      } catch (e: unknown) {
        emitWernerExperience("fail");
        setError(e instanceof Error ? e.message : String(e));
        setHits(null);
      } finally {
        setBusy(false);
      }
    },
    [themeContext],
  );

  const onSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      void run(query, null);
    },
    [query, run],
  );

  // File-drop = a query signal. Read a bounded text prefix in the browser and
  // search on it; the file is never sent to the server / ingested.
  const biasFromFile = useCallback(
    async (file: File) => {
      try {
        const text = (await file.text()).slice(0, MAX_FILE_QUERY_CHARS);
        if (!text.trim()) {
          setError("That file has no readable text to search by.");
          return;
        }
        setQuery("");
        await run(text, `books like “${file.name}”`);
      } catch {
        setError("Couldn’t read that file.");
      }
    },
    [run],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files?.[0];
      if (file) void biasFromFile(file);
    },
    [biasFromFile],
  );

  const clear = useCallback(() => {
    setQuery("");
    setHits(null);
    setSignal(null);
    setError(null);
  }, []);

  return (
    <section
      data-testid="corpus-search"
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
      className={`rounded-md border px-3 py-3 transition-colors ${
        dragOver
          ? "border-aurora bg-aurora/10"
          : "border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-2"
      }`}
    >
      <form onSubmit={onSubmit} className="flex items-center gap-2">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search your books — or drop a file to find books like it"
          aria-label="Search the corpus"
          className="flex-1 bg-ice-0 dark:bg-charcoal-1 text-ink dark:text-bright rounded-md px-3 py-1.5 text-sm outline-none border border-rule dark:border-charcoal-1"
        />
        <LemonButton type="submit" size="sm" variant="primary" disabled={busy}>
          {busy ? "Searching…" : "Search"}
        </LemonButton>
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          aria-label="Choose a file to find similar books"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void biasFromFile(f);
            e.target.value = "";
          }}
        />
        <LemonButton
          type="button"
          size="sm"
          variant="tertiary"
          onClick={() => fileInputRef.current?.click()}
        >
          ＋ File
        </LemonButton>
      </form>

      {/* Honest signal: SAY what biased these results. */}
      {signal && (
        <p className="mt-2 text-[12px] font-serif text-shadow-1 dark:text-moonlight" data-testid="corpus-search-signal">
          Showing {signal}
          {themeContext && themeContext.length > 0 ? ", leaning on your active research" : ""}.
        </p>
      )}

      {error && (
        <p className="mt-2 text-[13px] text-emperor" role="alert">
          {error}
        </p>
      )}

      {hits !== null && (
        <div className="mt-2">
          {hits.length === 0 ? (
            <p className="text-[13px] text-shadow-1 dark:text-moonlight italic">
              Nothing in your corpus matched. Try different words.
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5" aria-label="Search results">
              {hits.map((h) => (
                <li key={h.chunk_id}>
                  <button
                    type="button"
                    onClick={() => onOpen(h.document_id, h.page_resolved ? h.page_index : null)}
                    className="w-full text-left rounded px-2 py-1.5 hover:bg-ice-3 dark:hover:bg-charcoal-1"
                  >
                    <span className="block text-[13px] font-serif text-ink dark:text-bright truncate">
                      {h.document_title ?? h.document_id}
                      {h.page_resolved && h.page_index !== null ? (
                        <span className="ml-2 text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                          p.{h.page_index + 1}
                        </span>
                      ) : (
                        <span className="ml-2 text-[11px] font-mono text-shadow-1 dark:text-moonlight italic">
                          open the book
                        </span>
                      )}
                    </span>
                    <span className="block text-[12px] text-shadow-1 dark:text-moonlight line-clamp-2">
                      {h.snippet}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            onClick={clear}
            className="mt-2 text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
          >
            clear search
          </button>
        </div>
      )}
    </section>
  );
}
