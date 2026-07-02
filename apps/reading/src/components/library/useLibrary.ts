import { useCallback, useEffect, useRef, useState } from "react";

import { API_BASE, apiFetch } from "../../lib/api";
import type { BookSummary, Servability } from "../../api/books";

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
 * GRACEFUL DEGRADATION: current builds register the route in `create_app`, but
 * older/down deployments can still 404 it. A 404 is surfaced as an honest,
 * recoverable `routeAbsent` state — the view shows "the catalog isn't
 * available yet", NEVER a blank shelf masquerading as an empty corpus (honesty
 * over a false-empty).
 */

/** The library filter — matches Unit A's `filter` query param exactly. */
export type LibraryFilter = "servable" | "gated" | "all";

/** Mirrors `LibraryPage` in interfaces/research/api/library.py. `works` reuses
 *  the `/books` `BookSummary` shape; `total` is the pre-pagination matched count
 *  so the surface can render a pager. */
export interface LibraryPage {
  works: BookSummary[];
  total: number;
  page: number;
  page_size: number;
}

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
  /** True when `/library` returned 404 — the deployed catalog route is absent.
   *  The surface states this honestly rather than showing a false-empty shelf. */
  routeAbsent: boolean;
  /** Re-run the current query (e.g. a retry button). */
  reload: () => void;
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function nullableString(value: unknown): string | null {
  return value == null ? null : nonEmptyString(value);
}

function safeCoverUri(value: unknown): string | null {
  const uri = nullableString(value);
  if (!uri) return null;
  if (/^data:image\/[a-z0-9.+-]+;base64,/i.test(uri)) return uri;
  try {
    const parsed = new URL(uri);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? uri : null;
  } catch {
    return null;
  }
}

function nonNegativeSafeInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? value
    : null;
}

function safeServability(value: unknown): Servability {
  switch (value) {
    case "public_domain":
    case "platform_authored":
    case "publisher_opted_in":
    case "source_declared_open":
    case "gated_metadata_only":
    case "taken_down":
      return value;
    default:
      return "gated_metadata_only";
  }
}

function safeLibraryWork(value: unknown): BookSummary | null {
  const work = record(value);
  if (!work) return null;
  const documentId = nonEmptyString(work.document_id);
  if (!documentId) return null;
  const servability = safeServability(work.servability);
  const takenDown = work.taken_down === true || servability === "taken_down";
  return {
    document_id: documentId,
    title: nullableString(work.title),
    author: nullableString(work.author),
    servability,
    servable_full_text:
      work.servable_full_text === true &&
      !takenDown &&
      servability !== "gated_metadata_only",
    page_count: nonNegativeSafeInteger(work.page_count) ?? 0,
    cover_uri: safeCoverUri(work.cover_uri),
    ip_holder_id: nullableString(work.ip_holder_id),
    taken_down: takenDown,
  };
}

function safeLibraryPage(value: unknown, args: UseLibraryArgs): LibraryPage {
  const body = record(value);
  const seen = new Set<string>();
  const works = Array.isArray(body?.works)
    ? body.works.flatMap((item) => {
        const work = safeLibraryWork(item);
        if (!work || seen.has(work.document_id)) return [];
        seen.add(work.document_id);
        return [work];
      })
    : [];
  return {
    works,
    total: nonNegativeSafeInteger(body?.total) ?? works.length,
    page: nonNegativeSafeInteger(body?.page) ?? args.page,
    page_size: nonNegativeSafeInteger(body?.page_size) ?? args.pageSize ?? 20,
  };
}

/** Fetch one library page. Throws `library_route_absent` on a 404 so the hook
 *  can distinguish an absent catalog route from an empty corpus and from a real
 *  error. */
export async function fetchLibraryPage(args: UseLibraryArgs): Promise<LibraryPage> {
  const params = new URLSearchParams({
    filter: args.filter,
    search: args.search,
    page: String(args.page),
    page_size: String(args.pageSize ?? 20),
  });
  const resp = await apiFetch(`${API_BASE}/library?${params.toString()}`);
  if (resp.status === 404) throw new Error("library_route_absent");
  if (!resp.ok) throw new Error(`GET /library: HTTP ${resp.status}`);
  return safeLibraryPage(await resp.json(), args);
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
