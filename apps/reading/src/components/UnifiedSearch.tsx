import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { corpusSearch } from "../api/corpusSearch";
import type { CorpusSearchHit } from "../api/corpusSearch";
import { useStartInvestigation } from "../hooks/useStartInvestigation";
import { useProviderKeys } from "../hooks/useProviderKeys";
import { useOpenDocument } from "../lib/openDocument";
import type { ResearchTier } from "../lib/api";
import LemonButton from "./lemon/LemonButton";
import Thinking from "../shared/Thinking";
import AIActionFailure from "../shared/AIActionFailure";
import { CelebrateBurst, useCelebrate } from "../shared/delight";
import GlassSurface from "../shell/GlassSurface";
import MyResearch from "../modes/ResearchWorkstation/MyResearch";

/**
 * UnifiedSearch — one agentic search box (antiek-reader SPR-08 M1–M5).
 *
 * Progressive disclosure in a single surface:
 *   • Keystrokes → live local vector hits via ``corpusSearch.ts`` (no key).
 *   • Enter (or "Research this") → the SPR-04 loop via ``useStartInvestigation``
 *     → ``startInvestigation`` (cassette-tested; inert until activation SPR-03).
 *   • Every result — local hit or research source — opens via ``openDocument``.
 *
 * Replaces the separate CorpusSearch + StartResearch doors (M4). ⌘K stays a
 * pure-navigation palette — see handoff for the fold-vs-coexist decision.
 */

/** Bound the dropped-file text used as the query signal. */
const MAX_FILE_QUERY_CHARS = 2000;

/**
 * Instant-results latency budget (rigor #5).
 *
 * 500ms from debounce fire → hits rendered. Local ``/corpus/search`` is a
 * single indexed vector lookup (typically <100ms server-side); 200ms debounce
 * + 300ms for RTT/render keeps the box honest without feeling sluggish.
 */
export const INSTANT_RESULTS_LATENCY_BUDGET_MS = 500;

/** Debounce before firing corpusSearch — keystrokes batch, Enter does not wait. */
const SEARCH_DEBOUNCE_MS = 200;

const EXAMPLE_PROMPTS: readonly string[] = [
  "What's the strongest case against this thesis?",
  "Trace how this idea evolved across my sources.",
  "Where do these authors disagree?",
];

const RESEARCH_TIER_OPTIONS: ReadonlyArray<{
  value: ResearchTier;
  label: string;
  hint: string;
}> = [
  { value: "fast", label: "Fast", hint: "cheaper, lower-latency" },
  { value: "deep", label: "Deep", hint: "reasoning-heavier" },
];
const DEFAULT_TIER: ResearchTier = "deep";

/** A web/graph source surfaced from an escalated research run. */
export interface ResearchSourceHit {
  kind: "research";
  document_id: string;
  document_title: string | null;
  chunk_id: string | null;
  snippet: string;
}

export type UnifiedSearchResult = CorpusSearchHit | ResearchSourceHit;

export interface UnifiedSearchProps {
  /** ``library`` — Read door shelf search. ``research`` — Research home entry. */
  variant?: "library" | "research";
  /** Active-research theme terms folded into the local query when present. */
  themeContext?: string[];
  /** Research home: composer above the MyResearch log (SPR-05 M3). */
  embedded?: boolean;
}

function isResearchHit(r: UnifiedSearchResult): r is ResearchSourceHit {
  return "kind" in r && r.kind === "research";
}

export default function UnifiedSearch({
  variant = "library",
  themeContext,
  embedded = false,
}: UnifiedSearchProps) {
  const navigate = useNavigate();
  const openDocument = useOpenDocument();
  const providerKeys = useProviderKeys();
  const start = useStartInvestigation();
  const { celebrating, celebrate } = useCelebrate();

  const [query, setQuery] = useState("");
  const [localHits, setLocalHits] = useState<CorpusSearchHit[] | null>(null);
  const [researchHits, setResearchHits] = useState<ResearchSourceHit[]>([]);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [signal, setSignal] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [tier, setTier] = useState<ResearchTier>(DEFAULT_TIER);
  const [needsKeyDismissed, setNeedsKeyDismissed] = useState(false);
  const [lastSearchLatencyMs, setLastSearchLatencyMs] = useState<number | null>(
    null,
  );

  const fileInputRef = useRef<HTMLInputElement>(null);
  const searchGenRef = useRef(0);
  const searchStartedAtRef = useRef<number | null>(null);
  const celebratedRef = useRef(false);

  const themedQuery = useCallback(
    (raw: string) => {
      const q = raw.trim();
      if (!q) return "";
      return themeContext && themeContext.length > 0
        ? `${q}\n\n(in the context of: ${themeContext.slice(0, 4).join(", ")})`
        : q;
    },
    [themeContext],
  );

  const runLocalSearch = useCallback(
    async (rawQuery: string, signalLabel: string | null) => {
      const q = rawQuery.trim();
      if (!q) {
        setLocalHits(null);
        setSignal(null);
        setSearchError(null);
        setLastSearchLatencyMs(null);
        return;
      }
      const gen = ++searchGenRef.current;
      searchStartedAtRef.current = performance.now();
      setSearchBusy(true);
      setSearchError(null);
      try {
        const res = await corpusSearch(themedQuery(q));
        if (gen !== searchGenRef.current) return;
        setLocalHits(res.hits);
        setSignal(signalLabel);
        const elapsed = performance.now() - (searchStartedAtRef.current ?? 0);
        setLastSearchLatencyMs(Math.round(elapsed));
      } catch (e: unknown) {
        if (gen !== searchGenRef.current) return;
        setSearchError(e instanceof Error ? e.message : String(e));
        setLocalHits(null);
        setLastSearchLatencyMs(null);
      } finally {
        if (gen === searchGenRef.current) setSearchBusy(false);
      }
    },
    [themedQuery],
  );

  // Keystrokes → debounced local vector search (M1). Empty query → sensible default.
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setLocalHits(null);
      setSignal(null);
      setSearchError(null);
      setLastSearchLatencyMs(null);
      return;
    }
    const t = window.setTimeout(() => {
      void runLocalSearch(q, null);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(t);
  }, [query, runLocalSearch]);

  const escalateBlocked =
    providerKeys.status === "loading" ||
    ((providerKeys.status === "absent" || providerKeys.status === "error") &&
      !needsKeyDismissed);

  const onEscalate = useCallback(async () => {
    const q = query.trim();
    if (q.length < 3) return;

    // Wait for the activation probe before escalating — never POST into the void.
    if (providerKeys.status === "loading") return;

    if (providerKeys.status === "absent" || providerKeys.status === "error") {
      setNeedsKeyDismissed(false);
      return;
    }

    setResearchHits([]);
    const id = await start.submit({ question: q, researchTier: tier });
    if (id) setQuery(q);
  }, [query, providerKeys.status, start, tier]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key !== "Enter" || e.shiftKey) return;
      e.preventDefault();
      void onEscalate();
    },
    [onEscalate],
  );

  const biasFromFile = useCallback(
    async (file: File) => {
      try {
        const text = (await file.text()).slice(0, MAX_FILE_QUERY_CHARS);
        if (!text.trim()) {
          setSearchError("That file has no readable text to search by.");
          return;
        }
        setQuery("");
        await runLocalSearch(text, `books like "${file.name}"`);
      } catch {
        setSearchError("Couldn't read that file.");
      }
    },
    [runLocalSearch],
  );

  const openResult = useCallback(
    (hit: UnifiedSearchResult) => {
      if (isResearchHit(hit)) {
        openDocument(
          hit.document_id,
          hit.chunk_id ? { chunkId: hit.chunk_id } : undefined,
        );
        return;
      }
      openDocument(
        hit.document_id,
        hit.page_resolved && hit.page_index !== null && hit.page_index >= 0
          ? { page: hit.page_index, chunkId: hit.chunk_id }
          : { chunkId: hit.chunk_id },
      );
    },
    [openDocument],
  );

  // Parse research sources from the live stream (SPR-04 loop output).
  // Payload shape varies by step — we key off document_id presence, not a
  // single action_type (the codegen ActionType union does not list every
  // runner-emitted step name yet).
  useEffect(() => {
    const sources: ResearchSourceHit[] = [];
    const seen = new Set<string>();
    for (const e of start.events) {
      const p = e.payload as unknown as Record<string, unknown> | undefined;
      const docId =
        typeof p?.document_id === "string"
          ? p.document_id
          : typeof p?.source_document_id === "string"
            ? p.source_document_id
            : null;
      if (!docId || seen.has(docId)) continue;
      seen.add(docId);
      sources.push({
        kind: "research",
        document_id: docId,
        document_title:
          typeof p?.document_title === "string"
            ? p.document_title
            : typeof p?.title === "string"
              ? p.title
              : null,
        chunk_id: typeof p?.chunk_id === "string" ? p.chunk_id : null,
        snippet:
          typeof p?.snippet === "string"
            ? p.snippet
            : "Research source",
      });
    }
    if (sources.length > 0) setResearchHits(sources);
  }, [start.events]);

  const startedAndLive = Boolean(start.startedId) && !start.failed;
  useEffect(() => {
    if (startedAndLive && !celebratedRef.current) {
      celebratedRef.current = true;
      celebrate();
    }
    if (!start.startedId) celebratedRef.current = false;
  }, [startedAndLive, start.startedId, celebrate]);

  const showNeedsKey =
    (providerKeys.status === "absent" || providerKeys.status === "error") &&
    query.trim().length >= 3 &&
    !needsKeyDismissed &&
    !start.startedId;

  const inputPlaceholder =
    variant === "research"
      ? "Search your library — press Enter to research the web"
      : "Search your books — or drop a file to find books like it";

  const searchPanel = (
    <section
      data-testid="unified-search"
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file) void biasFromFile(file);
      }}
      className={
        variant === "library"
          ? `rounded-md border px-3 py-3 transition-colors ${
              dragOver
                ? "border-aurora bg-aurora/10"
                : "border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-2"
            }`
          : "flex flex-col gap-3"
      }
    >
      <div className={variant === "library" ? "flex items-center gap-2" : "flex flex-col gap-2"}>
        <input
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setNeedsKeyDismissed(false);
          }}
          onKeyDown={onKeyDown}
          placeholder={inputPlaceholder}
          aria-label="Unified search"
          autoFocus={variant === "research"}
          disabled={start.busy || Boolean(start.startedId && !start.failed)}
          className={
            variant === "library"
              ? "flex-1 bg-ice-0 dark:bg-charcoal-1 text-ink dark:text-bright rounded-md px-3 py-1.5 text-sm outline-none border border-rule dark:border-charcoal-1"
              : "w-full font-serif text-[15px] leading-relaxed bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright rounded-hog border border-rule dark:border-charcoal-1 px-3 py-2 outline-none"
          }
        />
        {variant === "library" && (
          <>
            <LemonButton
              type="button"
              size="sm"
              variant="tertiary"
              onClick={() => fileInputRef.current?.click()}
            >
              ＋ File
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
          </>
        )}
        <LemonButton
          type="button"
          size="sm"
          variant="primary"
          onClick={() => void onEscalate()}
          disabled={
            start.busy ||
            query.trim().length < 3 ||
            Boolean(start.startedId && !start.failed) ||
            escalateBlocked
          }
          title="Escalate this query to agentic research (graph + web)"
        >
          {start.busy ? "Starting…" : "Research this"}
        </LemonButton>
      </div>

      {variant === "research" && (
        <div
          className="flex items-center gap-2"
          role="radiogroup"
          aria-label="Research depth"
        >
          <span className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
            Depth
          </span>
          <div className="inline-flex rounded-hog border border-rule dark:border-charcoal-1 overflow-hidden">
            {RESEARCH_TIER_OPTIONS.map((opt) => {
              const active = tier === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => setTier(opt.value)}
                  disabled={start.busy}
                  title={opt.hint}
                  className={
                    "px-3 py-1 text-[12px] font-mono transition-colors disabled:opacity-50 " +
                    (active
                      ? "bg-sun text-ink"
                      : "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright hover:bg-sun/10")
                  }
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      <p className="text-[11px] font-mono text-ink-mute dark:text-moonlight" role="note">
        Type for instant local hits (no key).{" "}
        <kbd className="border border-ink dark:border-bright rounded px-1 text-[10px]">↵</kbd>{" "}
        escalates the same query to agentic research.
      </p>

      {signal && (
        <p className="text-[12px] font-serif text-shadow-1 dark:text-moonlight" data-testid="unified-search-signal">
          Showing {signal}
          {themeContext && themeContext.length > 0 ? ", leaning on your active research" : ""}.
        </p>
      )}

      {searchError && (
        <p className="text-[13px] text-emperor" role="alert">
          {searchError}
        </p>
      )}

      {showNeedsKey && (
        <div
          role="status"
          data-testid="unified-search-needs-key"
          className="rounded-md border border-sun/50 bg-sun/10 px-3 py-2 text-[13px] font-serif text-ink dark:text-bright"
        >
          <p>
            Agentic research needs a provider key — the wiring is ready and waits on{" "}
            <strong>activation SPR-03</strong>. Local search above still works with no key.
          </p>
          <button
            type="button"
            className="mt-1 text-[11px] font-mono underline"
            onClick={() => setNeedsKeyDismissed(true)}
          >
            Dismiss
          </button>
        </div>
      )}

      {query.trim().length === 0 && !start.startedId && (
        <p className="text-[13px] text-shadow-1 dark:text-moonlight italic" data-testid="unified-search-empty">
          {variant === "research"
            ? "Ask a question — local hits appear as you type; Enter researches across your corpus and the web."
            : "Search your owned corpus — results appear as you type."}
        </p>
      )}

      {searchBusy && query.trim().length > 0 && (
        <p className="text-[12px] text-shadow-1 dark:text-moonlight italic" role="status">
          Searching locally…
        </p>
      )}

      {localHits !== null && query.trim().length > 0 && !searchBusy && (
        <div data-testid="unified-search-local-results">
          {localHits.length === 0 ? (
            <p className="text-[13px] text-shadow-1 dark:text-moonlight italic">
              Nothing in your corpus matched. Press Enter to research the web.
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5" aria-label="Local search results">
              {localHits.map((h) => (
                <li key={h.chunk_id}>
                  <button
                    type="button"
                    onClick={() => openResult(h)}
                    className="w-full text-left rounded px-2 py-1.5 hover:bg-ice-3 dark:hover:bg-charcoal-1"
                  >
                    <span className="block text-[13px] font-serif text-ink dark:text-bright truncate">
                      <span className="text-[10px] font-mono uppercase text-shadow-1 mr-1">
                        library
                      </span>
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
          {lastSearchLatencyMs !== null && (
            <p
              className="mt-1 text-[10px] font-mono text-ink-mute dark:text-moonlight"
              data-testid="unified-search-latency"
              data-latency-ms={lastSearchLatencyMs}
            >
              Local results in {lastSearchLatencyMs}ms (budget {INSTANT_RESULTS_LATENCY_BUDGET_MS}ms)
            </p>
          )}
        </div>
      )}

      {researchHits.length > 0 && (
        <ul className="flex flex-col gap-1.5 mt-2" aria-label="Research sources" data-testid="unified-search-research-results">
          {researchHits.map((h) => (
            <li key={`${h.document_id}:${h.chunk_id ?? "root"}`}>
              <button
                type="button"
                onClick={() => openResult(h)}
                className="w-full text-left rounded px-2 py-1.5 hover:bg-ice-3 dark:hover:bg-charcoal-1"
              >
                <span className="block text-[13px] font-serif text-ink dark:text-bright truncate">
                  <span className="text-[10px] font-mono uppercase text-aurora mr-1">web</span>
                  {h.document_title ?? h.document_id}
                </span>
                <span className="block text-[12px] text-shadow-1 dark:text-moonlight line-clamp-2">
                  {h.snippet}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {start.startedId && !start.failed && (
        <div
          className="mt-3 text-center"
          role="status"
          aria-live="polite"
          data-testid="unified-search-research-live"
        >
          <div className="relative flex items-center justify-center mb-2">
            {celebrating && (
              <CelebrateBurst active size={40} className="absolute inset-0 items-center justify-center" />
            )}
            <Thinking
              size={40}
              label={
                start.phase === "connecting"
                  ? "Connecting to the investigation"
                  : "The investigation is working"
              }
            />
          </div>
          <p className="text-sm font-serif text-ink dark:text-bright">
            Researching "{query.trim()}"…
          </p>
          <p className="text-xs font-mono text-ink-mute dark:text-moonlight">
            {start.events.length} event{start.events.length === 1 ? "" : "s"} · $
            {start.liveCost.toFixed(4)}
          </p>
          <button
            type="button"
            className="mt-2 text-xs font-mono underline text-shadow-1 dark:text-moonlight"
            onClick={() => navigate(`/inv/${start.startedId}`)}
          >
            Open full investigation →
          </button>
        </div>
      )}

      {start.failed && (
        <AIActionFailure
          title="The research didn't complete"
          reason={start.failureReason}
          onRetry={() => start.reset()}
        />
      )}

      {start.error && (
        <p className="text-xs font-mono text-emperor" role="alert">
          {start.error}
        </p>
      )}
    </section>
  );

  if (variant === "library") {
    return searchPanel;
  }

  // Research home — landing glass + optional log (M4 fold of StartResearch).
  return (
    <div
      className={
        embedded
          ? "h-full overflow-y-auto px-6 py-8"
          : "h-full flex items-center justify-center px-6"
      }
    >
      <GlassSurface
        variant="glass"
        className={
          (embedded ? "mx-auto w-full max-w-3xl" : "w-full max-w-xl") +
          " rounded-hog-lg px-6 py-7"
        }
      >
        <h1 className="text-2xl font-serif text-ink dark:text-bright mb-2 text-center">
          Search & research
        </h1>
        <p className="text-sm text-shadow-1 dark:text-moonlight leading-relaxed font-serif text-center mb-6">
          One box: instant local hits as you type, Enter to run the agentic loop
          across your corpus and the web. Every result opens in the one Reader.
        </p>

        {searchPanel}

        {variant === "research" && query.trim().length === 0 && !start.startedId && (
          <div className="mt-7">
            <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-2 text-center">
              Try one of these
            </p>
            <div className="flex flex-col gap-2">
              {EXAMPLE_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => setQuery(prompt)}
                  className="w-full text-left text-[13px] font-serif text-ink dark:text-bright px-3 py-2 rounded-hog border-edge border-sun bg-ice-0 dark:bg-charcoal-2"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {embedded && (
          <div className="mt-12 border-t border-rule dark:border-charcoal-1 pt-2">
            <MyResearch embedded />
          </div>
        )}
      </GlassSurface>
    </div>
  );
}