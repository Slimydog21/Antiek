import { useCallback, useEffect, useRef, useState } from "react";

import type { BookSummary } from "../../api/books";
import {
  fetchLibraryCatalog,
  LibraryCatalogHttpError,
  type LibraryFilter,
  type LibraryPage,
} from "../../api/libraryCatalog";

/**
 * useLibrary — the data hook for the M2 Library browse view (Read SPR-09).
 *
 * Consumes Unit A's `GET /library` (interfaces/research/api/library.py): a
 * paginated, filterable, searchable catalog over the SAME servable-corpus read
 * path `/books` exposes. Each `work` is the EXISTING `BookSummary` shape verbatim
 * — metadata + the derived `servability` / `servable_full_text` flags, and (the
 * §9.0 guarantee, inherited from the contract) NEVER a body. The only path that
 * can surface full text is `/books/{id}/full-text`, gated server-side.
 *
 * GRACEFUL DEGRADATION: the route is built by the parallel Unit A in the same
 * worktree but may not be registered in `create_app` yet (it 404s until wired).
 * A 404 (or a network failure) is surfaced as an honest, recoverable state via
 * `routeAbsent` — the view shows "the catalog isn't available yet", NEVER a
 * blank shelf masquerading as an empty corpus (honesty over a false-empty).
 */

export type { LibraryFilter, LibraryPage } from "../../api/libraryCatalog";

export interface UseLibraryArgs {
  filter: LibraryFilter;
  search: string;
  page: number;
  pageSize?: number;
}

export interface UseLibraryResult {
  works: BookSummary[];
  total: number;
  page: number;
  pageSize: number;
  loading: boolean;
  /** A real, surfaced error (a non-404 failure). Distinct from `routeAbsent`. */
  error: string | null;
  /** True when `/library` returned 404 — the backend route isn't wired yet.
   *  The surface states this honestly rather than showing a false-empty shelf. */
  routeAbsent: boolean;
  /** Re-run the current query (e.g. a retry button). */
  reload: () => void;
}

/** Fetch one library page. Throws `library_route_absent` on a 404 so the hook
 *  can distinguish "not wired yet" from "empty corpus" and from a real error. */
export async function fetchLibraryPage(
  args: UseLibraryArgs,
): Promise<LibraryPage> {
  try {
    return await fetchLibraryCatalog({
      filter: args.filter,
      search: args.search,
      page: args.page,
      page_size: args.pageSize ?? 20,
    });
  } catch (error) {
    if (error instanceof LibraryCatalogHttpError && error.status === 404) {
      throw new Error("library_route_absent", { cause: error });
    }
    throw error;
  }
}

export function useLibrary(args: UseLibraryArgs): UseLibraryResult {
  const { filter, search, page, pageSize = 20 } = args;
  const [works, setWorks] = useState<BookSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [routeAbsent, setRouteAbsent] = useState(false);
  // A monotonically increasing token so a slow in-flight request can't clobber
  // the result of a newer one (a fast typer changing `search` mid-fetch).
  const reqRef = useRef(0);
  const [reloadKey, setReloadKey] = useState(0);

  const reload = useCallback(() => setReloadKey((k) => k + 1), []);

  useEffect(() => {
    const token = ++reqRef.current;
    setLoading(true);
    setError(null);
    setRouteAbsent(false);
    fetchLibraryPage({ filter, search, page, pageSize })
      .then((data) => {
        if (token !== reqRef.current) return; // a newer request superseded us
        setWorks(data.works);
        setTotal(data.total);
      })
      .catch((e: unknown) => {
        if (token !== reqRef.current) return;
        setWorks([]);
        setTotal(0);
        if (e instanceof Error && e.message === "library_route_absent") {
          setRouteAbsent(true);
        } else {
          setError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (token === reqRef.current) setLoading(false);
      });
  }, [filter, search, page, pageSize, reloadKey]);

  return { works, total, page, pageSize, loading, error, routeAbsent, reload };
}
