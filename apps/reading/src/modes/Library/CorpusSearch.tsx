import { useCallback, useEffect, useRef, useState } from "react";

import { LemonButton } from "../../components/lemon";
import { corpusSearch } from "../../api/corpusSearch";
import type { CorpusSearchHit } from "../../api/corpusSearch";
import {
  awaitWorkspaceOwnerSession,
  isWorkspaceOwnerSession,
  subscribeWorkspaceOwnerAdmission,
  workspaceOwnerAdmission,
  workspaceOwnerSession,
  type WorkspaceOwnerSession,
} from "../../lib/accountWorkspaceOwner";

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
// Enough UTF8 bytes for the query prefix without decoding an unbounded file.
const MAX_FILE_QUERY_BYTES = 8 * 1024;

export interface CorpusSearchProps {
  /** Open a result's book in the reader (optionally at a page). */
  onOpen: (documentId: string, pageIndex?: number | null) => void;
  /** Active-research theme terms (M1 theme-context). Empty/undefined → the
   * search uses the raw query, degrading gracefully. */
  themeContext?: string[];
}

type SearchRequest = { readonly query: string; readonly signalLabel: string | null };
type SearchAttempt = {
  readonly id: number;
  readonly owner: WorkspaceOwnerSession;
  readonly controller: AbortController;
  readonly unsubscribe: () => void;
};
type SearchState =
  | { kind: "idle" }
  | { kind: "reading" }
  | { kind: "loading" }
  | { kind: "ready"; hits: CorpusSearchHit[]; signalLabel: string | null; attempt: SearchAttempt }
  | { kind: "failed"; message: string; request: SearchRequest | null; attempt: SearchAttempt };

type SearchBoundary = {
  readonly active: (attempt: SearchAttempt) => boolean;
  readonly current: (attempt: SearchAttempt) => boolean;
  readonly setState: (state: SearchState) => void;
};

type FileSearchBoundary = SearchBoundary & {
  readonly begin: (owner: WorkspaceOwnerSession) => SearchAttempt | null;
  readonly setDraft: (draft: { query: string; owner: WorkspaceOwnerSession }) => void;
  readonly run: (query: string, signalLabel: string | null, attempt: SearchAttempt) => void;
};

async function executeSearch(
  request: SearchRequest,
  attempt: SearchAttempt,
  { active, current, setState }: SearchBoundary,
) {
  setState({ kind: "loading" });
  do {
    if (!await awaitWorkspaceOwnerSession(attempt.owner, attempt.controller.signal) || !active(attempt)) return;
  } while (!current(attempt));
  try {
    const result = await corpusSearch(request.query);
    if (!active(attempt)) return;
    do {
      if (!await awaitWorkspaceOwnerSession(attempt.owner, attempt.controller.signal) || !active(attempt)) return;
    } while (!current(attempt));
    setState({ kind: "ready", hits: result.hits, signalLabel: request.signalLabel, attempt });
  } catch (error: unknown) {
    do {
      if (!await awaitWorkspaceOwnerSession(attempt.owner, attempt.controller.signal) || !active(attempt)) return;
    } while (!current(attempt));
    setState({ kind: "failed", message: error instanceof Error ? error.message : String(error), request, attempt });
  }
}

async function searchFromFile(
  file: File,
  { active, begin, current, run, setDraft, setState }: FileSearchBoundary,
) {
  const attempt = begin(workspaceOwnerSession());
  if (!attempt) return;
  setState({ kind: "reading" });
  try {
    const prefix = file.size <= MAX_FILE_QUERY_BYTES ? file : file.slice(0, MAX_FILE_QUERY_BYTES);
    const text = (await prefix.text()).slice(0, MAX_FILE_QUERY_CHARS);
    if (!active(attempt)) return;
    do {
      if (!await awaitWorkspaceOwnerSession(attempt.owner, attempt.controller.signal) || !active(attempt)) return;
    } while (!current(attempt));
    if (!text.trim()) {
      setState({ kind: "failed", message: "That file has no readable text to search by.", request: null, attempt });
      return;
    }
    setDraft({ query: "", owner: attempt.owner });
    run(text, `books like “${file.name}”`, attempt);
  } catch {
    do {
      if (!await awaitWorkspaceOwnerSession(attempt.owner, attempt.controller.signal) || !active(attempt)) return;
    } while (!current(attempt));
    setState({ kind: "failed", message: "Couldn’t read that file.", request: null, attempt });
  }
}

function SearchResults({ ready, onOpen }: {
  readonly ready: Extract<SearchState, { kind: "ready" }> | null;
  readonly onOpen: (hit: CorpusSearchHit, attempt: SearchAttempt) => Promise<void>;
}) {
  const hits = ready?.hits ?? null;
  return (
    <>
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
                    onClick={() => { if (ready) void onOpen(h, ready.attempt); }}
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
    </>
  );
}

export default function CorpusSearch({ onOpen, themeContext }: CorpusSearchProps) {
  const [draft, setDraft] = useState(() => ({ query: "", owner: workspaceOwnerSession() }));
  const query = draft.query;
  const [state, setState] = useState<SearchState>({ kind: "idle" });
  const [admission, setAdmission] = useState(workspaceOwnerAdmission);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const requestId = useRef(0);
  const attemptRef = useRef<SearchAttempt | null>(null);
  const live = useRef(true);
  const busy = state.kind === "loading" || state.kind === "reading";
  const ready = state.kind === "ready"
    && admission.state === "ready"
    && admission.session === state.attempt.owner
    && isWorkspaceOwnerSession(state.attempt.owner) ? state : null;
  const signal = ready?.signalLabel ?? null;

  const disposeAttempt = useCallback(() => {
    const previous = attemptRef.current;
    attemptRef.current = null;
    requestId.current += 1;
    previous?.unsubscribe();
    previous?.controller.abort();
  }, []);

  const retire = useCallback(() => {
    disposeAttempt();
    setState({ kind: "idle" });
  }, [disposeAttempt]);

  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
      disposeAttempt();
    };
  }, [disposeAttempt]);

  const create = useCallback((owner: WorkspaceOwnerSession): SearchAttempt | null => {
    const snapshot = workspaceOwnerAdmission();
    if (!live.current || snapshot.session !== owner
      || (snapshot.state !== "ready" && snapshot.state !== "suspended")) return null;
    disposeAttempt();
    let attempt: SearchAttempt | null = null;
    // Notifications can still fail in a later observer; this callback never dispatches.
    const observe = (next: ReturnType<typeof workspaceOwnerAdmission>) => {
      if (!attempt || attemptRef.current !== attempt) return;
      setAdmission(next);
      if (next.state === "retiring" || next.state === "failed" || next.session !== owner) {
        retire();
        setDraft({ query: "", owner: next.session });
      }
    };
    const unsubscribe = subscribeWorkspaceOwnerAdmission(observe);
    const captured = { id: requestId.current, owner, controller: new AbortController(), unsubscribe };
    attempt = captured;
    attemptRef.current = captured;
    observe(workspaceOwnerAdmission());
    return attemptRef.current === captured ? captured : null;
  }, [disposeAttempt, retire]);

  const active = useCallback((attempt: SearchAttempt) => {
    const snapshot = workspaceOwnerAdmission();
    return live.current && attemptRef.current === attempt
      && requestId.current === attempt.id && !attempt.controller.signal.aborted
      && attempt.owner.subject !== null && snapshot.session === attempt.owner
      && (snapshot.state === "ready" || snapshot.state === "suspended");
  }, []);

  const current = useCallback((attempt: SearchAttempt) => active(attempt)
    && isWorkspaceOwnerSession(attempt.owner), [active]);

  const begin = useCallback((owner: WorkspaceOwnerSession) =>
    owner.subject === null ? null : create(owner), [create]);

  const execute = useCallback((request: SearchRequest, attempt: SearchAttempt) =>
    executeSearch(request, attempt, { active, current, setState }), [active, current]);

  const run = useCallback((rawQuery: string, signalLabel: string | null, attempt: SearchAttempt) => {
    const q = rawQuery.trim();
    if (!q) { retire(); return; }
    const themed = themeContext && themeContext.length > 0
      ? `${q}\n\n(in the context of: ${themeContext.slice(0, 4).join(", ")})`
      : q;
    void execute({ query: themed, signalLabel }, attempt);
  }, [execute, retire, themeContext]);

  const onSubmit = useCallback((event: React.FormEvent) => {
    event.preventDefault();
    if (!query.trim()) return;
    const attempt = begin(draft.owner);
    if (attempt) run(query, null, attempt);
  }, [begin, draft.owner, query, run]);

  const biasFromFile = useCallback((file: File) =>
    searchFromFile(file, { active, begin, current, run, setDraft, setState }), [active, begin, current, run]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files?.[0];
      if (file) void biasFromFile(file);
    },
    [biasFromFile],
  );

  const changeQuery = useCallback((value: string) => {
    retire();
    const owner = workspaceOwnerSession();
    const resource = create(owner);
    setDraft({ query: resource ? value : "", owner });
  }, [create, retire]);

  const clear = useCallback(() => {
    retire();
    setDraft({ query: "", owner: workspaceOwnerSession() });
  }, [retire]);

  const retry = useCallback((request: SearchRequest, previous: SearchAttempt) => {
    if (!active(previous)) return;
    const attempt = begin(previous.owner);
    if (attempt) void execute(request, attempt);
  }, [active, begin, execute]);

  const open = useCallback(async (hit: CorpusSearchHit, attempt: SearchAttempt) => {
    do {
      if (!await awaitWorkspaceOwnerSession(attempt.owner, attempt.controller.signal) || !active(attempt)) return;
    } while (!current(attempt));
    onOpen(hit.document_id, hit.page_resolved ? hit.page_index : null);
  }, [active, current, onOpen]);

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
          onChange={(e) => changeQuery(e.target.value)}
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
              onClick={() => { if (state.request) retry(state.request, state.attempt); }}>
              Retry search
            </LemonButton>
          )}
        </div>
      )}

      <SearchResults ready={ready} onOpen={open} />
      {state.kind !== "idle" && (
        <button type="button" onClick={clear}
          className="mt-2 text-xs font-mono text-shadow-1 dark:text-moonlight hover:underline">
          clear search
        </button>
      )}
    </section>
  );
}
