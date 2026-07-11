/**
 * LibraryCatalogPanel — metadata-only catalog browser UI.
 *
 * Consumes GET /library via fetchLibraryCatalog (#812). Does not own
 * Library/index.tsx. Never renders body/full-text fields.
 */

import { useMemo, useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  fetchLibraryCatalog,
  formatServability,
  type LibraryFilter,
  type LibraryPage,
} from "../../api/libraryCatalog";

export interface LibraryCatalogPanelProps {
  fetchFn?: typeof fetchLibraryCatalog;
  initialFilter?: LibraryFilter;
  initialSearch?: string;
}

export default function LibraryCatalogPanel({
  fetchFn = fetchLibraryCatalog,
  initialFilter = "all",
  initialSearch = "",
}: LibraryCatalogPanelProps) {
  const [filter, setFilter] = useState<LibraryFilter>(initialFilter);
  const [search, setSearch] = useState(initialSearch);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LibraryPage | null>(null);

  const pageSize = 20;
  const totalPages = useMemo(() => {
    if (!result) return 0;
    return Math.max(1, Math.ceil(result.total / result.page_size));
  }, [result]);

  async function onLoad(nextPage = page) {
    setBusy(true);
    setError(null);
    try {
      const body = await fetchFn({
        filter,
        search,
        page: nextPage,
        page_size: pageSize,
      });
      setResult(body);
      setPage(body.page);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="library-catalog-panel">
      <LemonCard title="Library catalog" className="library-catalog-panel">
        <p className="text-sm opacity-80" data-testid="library-catalog-blurb">
          Browse hosted works as metadata-only summaries (title, author,
          servability). Full text is never shown here — open a work separately
          for HTML reading.
        </p>

        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Filter</span>
            <select
              className="rounded border border-border bg-bg-light px-2 py-1 text-sm"
              value={filter}
              onChange={(e) => setFilter(e.target.value as LibraryFilter)}
              data-testid="library-catalog-filter"
              aria-label="Catalog filter"
            >
              <option value="all">all</option>
              <option value="servable">servable</option>
              <option value="gated">gated</option>
            </select>
          </label>

          <label className="text-sm flex flex-col gap-1">
            <span>Search title/author</span>
            <LemonInput
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="scaling laws"
              data-testid="library-catalog-search"
              aria-label="Search title or author"
            />
          </label>

          <div className="flex gap-2 items-center">
            <LemonButton
              variant="primary"
              disabled={busy}
              onClick={() => void onLoad(1)}
              data-testid="library-catalog-load"
            >
              {busy ? "Loading…" : "Load catalog"}
            </LemonButton>
            {result ? (
              <>
                <LemonButton
                  disabled={busy || page <= 1}
                  onClick={() => void onLoad(page - 1)}
                  data-testid="library-catalog-prev"
                >
                  Prev
                </LemonButton>
                <LemonButton
                  disabled={busy || page >= totalPages}
                  onClick={() => void onLoad(page + 1)}
                  data-testid="library-catalog-next"
                >
                  Next
                </LemonButton>
              </>
            ) : null}
          </div>

          {error ? (
            <div className="text-sm text-danger" data-testid="library-catalog-error">
              {error}
            </div>
          ) : null}

          {result ? (
            <div data-testid="library-catalog-result" className="flex flex-col gap-2">
              <div data-testid="library-catalog-total">
                Total: {result.total} · page {result.page}/{totalPages} · size{" "}
                {result.page_size}
              </div>
              {result.works.length === 0 ? (
                <div data-testid="library-catalog-empty">No works match.</div>
              ) : (
                <ul data-testid="library-catalog-works">
                  {result.works.map((w) => (
                    <li
                      key={w.document_id}
                      data-testid={`library-work-${w.document_id}`}
                    >
                      <span data-testid={`library-work-title-${w.document_id}`}>
                        {w.title || "(untitled)"}
                      </span>
                      {" — "}
                      <span data-testid={`library-work-author-${w.document_id}`}>
                        {w.author || "(unknown author)"}
                      </span>
                      {" · "}
                      <span data-testid={`library-work-servability-${w.document_id}`}>
                        {formatServability(w)}
                      </span>
                      {" · pages "}
                      {w.page_count}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
