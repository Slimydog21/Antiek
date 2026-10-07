import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ErrorBanner, LemonButton, LemonInput } from "../lemon";
import { useLibrary, type LibraryFilter } from "./useLibrary";
import WorkCard from "./WorkCard";
import { LoadingState } from "../states";

/**
 * LibraryView — the M2 Library browse view (Read SPR-09), the paginated browse
 * surface over Unit A's `GET /library`.
 *
 * Cards (title/author/source/servability) + a servable|gated|all filter + a
 * title/author search + a pager, with honest loading / empty / route-absent
 * states. The §9.0 posture is in the IA: a servable work invites a Read, a gated
 * one offers metadata + a claim affordance — never a body request from the
 * shelf, never a broken open.
 *
 * Relationship to the existing `modes/Library`: that surface is the feature-rich
 * Read door (theme-ranking, prompt-to-curate, corpus search, meta-read). This
 * view is the SPR-09 browse primitive specifically over the new paginated
 * `/library` endpoint — composed from the spec-named primitives (useLibrary +
 * WorkCard). It is additive; it does not replace the door.
 */

const FILTERS: { key: LibraryFilter; label: string; hint: string }[] = [
  { key: "servable", label: "Shelf", hint: "Readable in full" },
  { key: "gated", label: "Preview", hint: "Metadata only — claim to read" },
  { key: "all", label: "All", hint: "Everything, flagged" },
];

export interface LibraryViewProps {
  /** Initial filter (defaults to the servable shelf — the legal posture leads
   *  with what can be read in full). */
  initialFilter?: LibraryFilter;
  pageSize?: number;
}

export default function LibraryView({
  initialFilter = "servable",
  pageSize = 24,
}: LibraryViewProps) {
  const navigate = useNavigate();
  const viewId = useId();
  const panelId = `${viewId}-works`;
  const panelRef = useRef<HTMLDivElement>(null);
  const filterRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [filter, setFilter] = useState<LibraryFilter>(initialFilter);
  // Debounced search: the input updates `draft` immediately (responsive field)
  // and `search` after a short pause (the actual query), so a fast typer does
  // not fire a request per keystroke.
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const t = setTimeout(() => setSearch(draft.trim()), 250);
    return () => clearTimeout(t);
  }, [draft]);

  // Changing the filter or the search resets to page 1 — a stale high page
  // number against a smaller matched set would render an empty page.
  useEffect(() => {
    setPage(1);
  }, [filter, search]);

  const { works, total, loading, error, routeAbsent, reload } = useLibrary({
    filter,
    search,
    page,
    pageSize,
  });

  const lastPage = Math.max(1, Math.ceil(total / pageSize));
  const reloadKeepingFocus = () => {
    const panel = panelRef.current;
    if (!panel?.isConnected) return;
    panel.focus({ preventScroll: true });
    reload();
  };
  const open = (documentId: string) =>
    navigate(`/read/${encodeURIComponent(documentId)}`);

  const handleFilterKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (
      event.defaultPrevented || event.nativeEvent.isComposing ||
      event.ctrlKey || event.metaKey || event.altKey || event.shiftKey ||
      event.target !== event.currentTarget
    ) return;

    let next: number;
    switch (event.key) {
      case "ArrowRight": next = (index + 1) % FILTERS.length; break;
      case "ArrowLeft": next = (index + FILTERS.length - 1) % FILTERS.length; break;
      case "Home": next = 0; break;
      case "End": next = FILTERS.length - 1; break;
      default: return;
    }
    const target = filterRefs.current[next];
    if (!target?.isConnected) return;
    event.preventDefault();
    setFilter(FILTERS[next].key);
    target.focus({ preventScroll: true });
  };

  const subtitle = useMemo(() => {
    if (loading) return "Loading the shelf…";
    if (routeAbsent) return "the catalog service isn’t available yet";
    if (error) return "The shelf did not load, so the count is unknown";
    if (filter === "servable") return `${total} readable in full`;
    if (filter === "gated") return `${total} preview-only titles`;
    return `${total} titles`;
  }, [loading, routeAbsent, error, filter, total]);

  return (
    <div className="max-w-5xl mx-auto px-8 py-10 space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-serif text-ink dark:text-bright">Library</h1>
        <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
          A licensed shelf of what can be aggregated — public-domain works,
          Antiek originals, and publisher-opted-in titles you can read in full.
          A library, not a marketplace: everything else is preview-only.{" "}
          {subtitle}.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <div role="tablist" aria-label="Corpus filter" className="flex items-center gap-2">
          {FILTERS.map((f, index) => (
            <button
              key={f.key}
              ref={(node) => { filterRefs.current[index] = node; }}
              id={`${viewId}-${f.key}`}
              role="tab"
              aria-selected={filter === f.key}
              aria-controls={panelId}
              tabIndex={filter === f.key ? 0 : -1}
              type="button"
              title={f.hint}
              onClick={() => setFilter(f.key)}
              onKeyDown={(event) => handleFilterKeyDown(event, index)}
              className={`px-3 py-1 rounded-md text-xs font-mono transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun focus-visible:outline-offset-2 ${
                filter === f.key
                  ? "bg-ink text-white"
                  : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright hover:bg-ice-4"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="flex-1 min-w-[180px]">
          <LemonInput
            sizing="sm"
            type="search"
            placeholder="Search title or author…"
            aria-label="Search the library by title or author"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            wrapperClassName="w-full"
          />
        </div>
      </div>

      <div
        ref={panelRef}
        id={panelId}
        role="tabpanel"
        tabIndex={-1}
        aria-labelledby={`${viewId}-${filter}`}
        className="space-y-6 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun focus-visible:outline-offset-4"
      >
        {routeAbsent && (
          <div className="text-sm border-edge border-sun rounded-md bg-sun/15 px-3 py-2 text-ink dark:text-bright flex items-center justify-between gap-3">
            <span>
              The catalog isn’t available yet — the library service hasn’t come up.
              This is an honest “not ready”, not an empty shelf.
            </span>
            <LemonButton size="sm" type="button" variant="tertiary" onClick={reloadKeepingFocus}>
              Retry
            </LemonButton>
          </div>
        )}

        {error && (
          <ErrorBanner className="flex items-center justify-between gap-3">
            <span>{error}</span>
            <LemonButton size="sm" type="button" variant="tertiary" onClick={reloadKeepingFocus}>
              Retry
            </LemonButton>
          </ErrorBanner>
        )}

        {loading && (
          <LoadingState variant="inline" label="Opening the library" />
        )}

        {!loading && !error && !routeAbsent && works.length === 0 && (
          <p className="text-sm text-shadow-1 dark:text-moonlight italic">
            {search
              ? `Nothing matched “${search}”. Try different words, or clear the search.`
              : filter === "servable"
                ? "Nothing is readable in full on the shelf yet — the library only shows what can be legally aggregated. Check the Preview tab for titles you can sample."
                : "Nothing here."}
          </p>
        )}

        {works.length > 0 && (
          <section
            aria-label="Works"
            className="grid gap-5"
            style={{ gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))" }}
          >
            {works.map((w) => (
              // Servable → the reader. Gated → the reader's gate-safe metadata +
              // preview-only surface (it shows the record + a bounded, server-
              // gated snippet — it NEVER serves the full body, so this is a claim/
              // metadata affordance, not a broken open). Removed works are
              // non-actionable in the card itself.
              <WorkCard key={w.document_id} work={w} onRead={open} onClaim={open} />
            ))}
          </section>
        )}

        {!loading && !error && !routeAbsent && total > pageSize && (
          <nav
            aria-label="Library pages"
            className="flex items-center justify-between border-t border-rule dark:border-charcoal-1 pt-3"
          >
            <LemonButton
              size="sm"
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ← Previous
            </LemonButton>
            <span className="text-xs font-mono text-shadow-1 dark:text-moonlight">
              Page {page} of {lastPage}
            </span>
            <LemonButton
              size="sm"
              type="button"
              disabled={page >= lastPage}
              onClick={() => setPage((p) => Math.min(lastPage, p + 1))}
            >
              Next →
            </LemonButton>
          </nav>
        )}
      </div>
    </div>
  );
}
