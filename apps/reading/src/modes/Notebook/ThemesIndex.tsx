// SPR-11 / M4 — Themes index page.
//
// Route: /wrestle/themes
//
// Lists every theme for the authenticated user. Includes the
// auto-suggest stub section per M6.
//
// Sort: last_edited_desc default; toggle to title_asc.
// Search: substring filter on title (case-insensitive).
// Empty state: "Promote blocks from any document to start a theme."
//
// Sprint 19 coordination (rigor #4): the Brainstorming Workstation
// is the natural future home for this surface (Surface E in the
// master-spec language). Sprint 19's spec has not landed yet
// (specs/wrestle-evolution/ contains sprint-01 through sprint-11
// only at 2026-05-21); the existing apps/reading/src/modes/
// BrainstormStation/ surface targets Sprint 17 scope (parked-
// questions + watch-for-later). When Sprint 19 lands and exposes
// a host surface, this index can be moved into a panel; the
// standalone route + the underlying API contract stay valid
// either way.

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  ThemeApiError,
  listThemes,
  type ThemeCard,
} from "../../../api/themes/by-slug";
import SuggestedThemes from "./SuggestedThemes";

export type ThemesIndexSort = "last_edited_desc" | "title_asc";

export default function ThemesIndex(): JSX.Element {
  const [themes, setThemes] = useState<ThemeCard[] | null>(null);
  const [status, setStatus] =
    useState<"loading" | "ready" | "error" | "unimplemented">("loading");
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<ThemesIndexSort>("last_edited_desc");
  const [query, setQuery] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setError(null);
    void listThemes({ sort })
      .then((rows) => {
        if (cancelled) return;
        setThemes(rows);
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ThemeApiError && err.status === 404) {
          setStatus("unimplemented");
          setThemes([]);
          return;
        }
        setStatus("error");
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [sort]);

  // Client-side title filter; the server returns the full list and
  // we narrow on substring. Cheap for the SPR-11 single-operator
  // case; reconsider when multi-user themes land (out of scope).
  const filtered = useMemo(() => {
    if (!themes) return [];
    const q = query.trim().toLowerCase();
    if (!q) return themes;
    return themes.filter((t) => t.title.toLowerCase().includes(q));
  }, [themes, query]);

  return (
    <div className="flex flex-col h-screen bg-stone-50">
      <header className="flex items-center justify-between px-6 py-3 border-b border-stone-200 bg-white">
        <h1 className="text-sm font-serif text-stone-900">Themes</h1>
        <Link
          to="/wrestle"
          className="text-xs font-mono text-stone-500 hover:text-stone-900"
        >
          ← back to reading
        </Link>
      </header>

      <main className="flex-1 overflow-y-auto">
        <article className="max-w-4xl mx-auto px-8 py-10">
          {/* Toolbar */}
          <div className="flex flex-wrap items-center gap-3 mb-6">
            <input
              type="text"
              placeholder="Search themes…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="flex-1 min-w-[200px] border border-stone-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
              data-testid="themes-search"
            />
            <label className="text-xs font-mono text-stone-500 flex items-center gap-2">
              sort:
              <select
                value={sort}
                onChange={(e) =>
                  setSort(e.target.value as ThemesIndexSort)
                }
                className="border border-stone-300 rounded-md px-2 py-1 text-sm bg-white"
                data-testid="themes-sort"
              >
                <option value="last_edited_desc">last-edited</option>
                <option value="title_asc">title (A–Z)</option>
              </select>
            </label>
          </div>

          {/* States */}
          {status === "loading" && (
            <p className="text-sm text-stone-500">Loading themes…</p>
          )}
          {status === "error" && (
            <p className="text-sm font-mono text-red-700">
              Failed to load themes: {error}
            </p>
          )}
          {status === "unimplemented" && (
            <p className="text-xs font-mono text-amber-700 mb-4">
              Theme index API is not yet wired on the backend (404 from
              GET /api/themes). The surface is ready; the FastAPI route
              handler lands in a follow-up commit.
            </p>
          )}

          {status === "ready" && filtered.length === 0 && query.trim() === "" && (
            <div
              className="border border-dashed border-stone-300 rounded-md px-6 py-12 text-center"
              data-testid="themes-empty"
            >
              <p className="text-sm text-stone-700">
                Promote blocks from any document to start a theme.
              </p>
              <p className="mt-2 text-[11px] font-mono text-stone-500">
                Open a per-document notebook, select a block, and click
                "Promote to theme…".
              </p>
            </div>
          )}

          {status === "ready" && filtered.length === 0 && query.trim() !== "" && (
            <p className="text-sm text-stone-500 italic" data-testid="themes-no-match">
              No themes match "{query}".
            </p>
          )}

          {filtered.length > 0 && (
            <ul
              className="grid grid-cols-1 sm:grid-cols-2 gap-3"
              data-testid="themes-grid"
            >
              {filtered.map((t) => (
                <li key={t.theme_id}>
                  <Link
                    to={`/wrestle/themes/${encodeURIComponent(t.slug)}`}
                    className={
                      "block rounded-md border border-stone-200 bg-white " +
                      "p-4 hover:shadow-md hover:border-stone-400 transition-all"
                    }
                    data-testid={`theme-card-${t.theme_id}`}
                  >
                    <h3 className="text-sm font-serif text-stone-900">
                      {t.title}
                    </h3>
                    {t.cover_snippet && (
                      <p className="mt-1 text-xs text-stone-600 line-clamp-2">
                        {t.cover_snippet}
                      </p>
                    )}
                    <p className="mt-2 text-[11px] font-mono text-stone-500">
                      {t.block_count} block{t.block_count === 1 ? "" : "s"} ·{" "}
                      {formatRelative(t.last_edited_at)}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          )}

          {/* M6 — auto-suggest stub (always present below the grid) */}
          <SuggestedThemes />
        </article>
      </main>
    </div>
  );
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.max(0, now - then);
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}
