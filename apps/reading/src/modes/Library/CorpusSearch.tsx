import { useCallback, useEffect, useRef, useState } from "react";

import { LemonButton } from "../../components/lemon";
import { corpusSearch } from "../../api/corpusSearch";
import type { CorpusSearchHit } from "../../api/corpusSearch";

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

type SearchRequest = { query: string; signalLabel: string | null };
type SearchState =
  | { kind: "idle" }
  | { kind: "reading" }
  | { kind: "loading" }
  | { kind: "ready"; hits: CorpusSearchHit[]; signalLabel: string | null }
  | { kind: "failed"; message: string; request: SearchRequest | null };

export default function CorpusSearch({ onOpen, themeContext }: CorpusSearchProps) {
  const [query, setQuery] = useState("");
  const [state, setState] = useState<SearchState>({ kind: "idle" });
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const requestId = useRef(0);
  const busy = state.kind === "loading" || state.kind === "reading";
  const hits = state.kind === "ready" ? state.hits : null;
  const signal = state.kind === "ready" ? state.signalLabel : null;

  useEffect(() => () => { requestId.current += 1; }, []);

  const retire = useCallback(() => {
    requestId.current += 1;
    setState({ kind: "idle" });
  }, []);

  const execute = useCallback(async (request: SearchRequest, id: number) => {
    setState({ kind: "loading" });
    try {
      const result = await corpusSearch(request.query);
      if (requestId.current !== id) return;
      setState({ kind: "ready", hits: result.hits, signalLabel: request.signalLabel });
    } catch (error: unknown) {
      if (requestId.current !== id) return;
      setState({ kind: "failed", message: error instanceof Error ? error.message : String(error), request });
    }
  }, []);

  const run = useCallback(
    async (rawQuery: string, signalLabel: string | null, id = ++requestId.current) => {
      const q = rawQuery.trim();
      if (!q) { setState({ kind: "idle" }); return; }
      const themed = themeContext && themeContext.length > 0
        ? `${q}\n\n(in the context of: ${themeContext.slice(0, 4).join(", ")})`
        : q;
      await execute({ query: themed, signalLabel }, id);
    },
    [execute, themeContext],
  );

  const onSubmit = useCallback((event: React.FormEvent) => {
    event.preventDefault();
    void run(query, null);
  }, [query, run]);

  const biasFromFile = useCallback(async (file: File) => {
    const id = ++requestId.current;
    setState({ kind: "reading" });
    try {
      const text = (await file.text()).slice(0, MAX_FILE_QUERY_CHARS);
      if (requestId.current !== id) return;
      if (!text.trim()) {
        setState({ kind: "failed", message: "That file has no readable text to search by.", request: null });
        return;
      }
      setQuery("");
      await run(text, `books like “${file.name}”`, id);
    } catch {
      if (requestId.current !== id) return;
      setState({ kind: "failed", message: "Couldn’t read that file.", request: null });
    }
  }, [run]);

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
    retire();
    setQuery("");
  }, [retire]);

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
          ? "border-sun-deep bg-sun/10"
          : "border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-2"
      }`}
    >
      <form onSubmit={onSubmit} className="flex items-center gap-2">
        <input
          type="search"
          value={query}
          onChange={(e) => { retire(); setQuery(e.target.value); }}
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
        <p className="mt-2 text-xs font-serif text-shadow-1 dark:text-moonlight" data-testid="corpus-search-signal">
          Showing {signal}
          {themeContext && themeContext.length > 0 ? ", leaning on your active research" : ""}.
        </p>
      )}

      {state.kind === "failed" && (
        <div className="mt-2 flex items-center justify-between gap-3" role="alert">
          <p className="text-sm text-emperor">{state.message}</p>
          {state.request && (
            <LemonButton type="button" size="sm" variant="tertiary"
              onClick={() => { if (state.request) void execute(state.request, ++requestId.current); }}>
              Retry search
            </LemonButton>
          )}
        </div>
      )}

      {hits !== null && (
        <div className="mt-2">
          {hits.length === 0 ? (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">
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
                    <span className="block text-sm font-serif text-ink dark:text-bright truncate">
                      {h.document_title ?? h.document_id}
                      {h.page_resolved && h.page_index !== null ? (
                        <span className="ml-2 text-xs font-mono text-shadow-1 dark:text-moonlight">
                          p.{h.page_index + 1}
                        </span>
                      ) : (
                        <span className="ml-2 text-xs font-mono text-shadow-1 dark:text-moonlight italic">
                          open the book
                        </span>
                      )}
                    </span>
                    <span className="block text-xs text-shadow-1 dark:text-moonlight line-clamp-2">
                      {h.snippet}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

        </div>
      )}
      {state.kind !== "idle" && (
        <button type="button" onClick={clear}
          className="mt-2 text-xs font-mono text-shadow-1 dark:text-moonlight hover:underline">
          clear search
        </button>
      )}
    </section>
  );
}
