// SPR-11 / M2 — "Promote to theme..." picker.
//
// The affordance lives on every Tier-2 block in PerDocNotebook.tsx
// (the Tier-2 surface from SPR-08). Clicking opens this modal which:
//
//   1. Lists existing themes for the user (autocomplete on title).
//   2. Lets the operator pick one OR type a new title to create
//      a new theme inline.
//   3. On submit, calls promoteBlocksToTheme with the supplied
//      source_block_ids.
//
// Multi-select is supported: the parent can pass an array of block
// ids. The picker doesn't care about cardinality — same call shape.
//
// Behavior-event emit
// -------------------
// After the promote succeeds, the parent fires a behavior event so
// the reward proxy sees the Tier-2 → Tier-3 promotion. SPR-01's
// closed taxonomy does NOT currently include 'notebook_block_promoted'
// (see substrate/behavior/taxonomy.py BehaviorEventType). Per the
// sprint operator instructions, we leave a labeled TODO at the call
// site rather than emit a phantom type. The handoff flags this for
// taxonomy expansion in a future sprint.

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ThemeApiError,
  createTheme,
  listThemes,
  promoteBlocksToTheme,
  type ThemeCard,
} from "../../../api/themes/by-slug";

export interface PromoteToThemeProps {
  /** Tier-2 block ids to promote. May be one or many; multi-select
   *  ships the same call. */
  sourceBlockIds: string[];
  /** Closes the picker. */
  onClose: () => void;
  /** Fired after the promote (and any inline-create) succeeds.
   *  Argument is the theme id the blocks landed in so the caller
   *  can navigate or refresh. */
  onPromoted: (themeId: string, themeTitle: string) => void;
}

export default function PromoteToTheme(
  props: PromoteToThemeProps,
): JSX.Element {
  const [query, setQuery] = useState<string>("");
  const [themes, setThemes] = useState<ThemeCard[] | null>(null);
  const [loadStatus, setLoadStatus] =
    useState<"loading" | "ready" | "error" | "unimplemented">("loading");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Load existing themes on mount.
  useEffect(() => {
    let cancelled = false;
    setLoadStatus("loading");
    void listThemes()
      .then((rows) => {
        if (cancelled) return;
        setThemes(rows);
        setLoadStatus("ready");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ThemeApiError && err.status === 404) {
          // Backend route not wired yet — degrade gracefully.
          setLoadStatus("unimplemented");
          setThemes([]);
          return;
        }
        setLoadStatus("error");
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Filter on the typed query — both substring and case-insensitive.
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!themes) return [];
    if (!q) return themes;
    return themes.filter((t) => t.title.toLowerCase().includes(q));
  }, [query, themes]);

  // "+ New theme" appears when the query doesn't exactly match
  // an existing theme's title (case-insensitive). Hitting Enter
  // when nothing in the list is selected creates the new theme.
  const exactMatch = useMemo(
    () =>
      themes?.find(
        (t) => t.title.toLowerCase() === query.trim().toLowerCase(),
      ) ?? null,
    [query, themes],
  );

  const showCreateOption = query.trim().length > 0 && !exactMatch;

  // ── Submit handlers ──

  const promote = useCallback(
    async (theme: ThemeCard) => {
      setSubmitting(true);
      setError(null);
      try {
        await promoteBlocksToTheme(theme.theme_id, {
          source_block_ids: props.sourceBlockIds,
        });
        props.onPromoted(theme.theme_id, theme.title);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setSubmitting(false);
      }
    },
    [props],
  );

  const createAndPromote = useCallback(async () => {
    const title = query.trim();
    if (!title) return;
    setSubmitting(true);
    setError(null);
    try {
      const newTheme = await createTheme({ title });
      await promoteBlocksToTheme(newTheme.theme_id, {
        source_block_ids: props.sourceBlockIds,
      });
      props.onPromoted(newTheme.theme_id, newTheme.title);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }, [query, props]);

  // Keyboard: Escape closes; Enter creates if "+ New theme" is the
  // active option; otherwise picks the first filtered theme.
  const onKey = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "Escape") {
        e.preventDefault();
        props.onClose();
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (filtered.length > 0) {
          void promote(filtered[0]);
        } else if (showCreateOption) {
          void createAndPromote();
        }
      }
    },
    [filtered, props, promote, createAndPromote, showCreateOption],
  );

  // ── Render ──

  return (
    <div
      className="fixed inset-0 z-40 bg-stone-900/40 backdrop-blur-sm flex items-start justify-center pt-24"
      onKeyDown={onKey}
      data-testid="promote-to-theme-modal"
    >
      <div
        className="bg-white border border-stone-300 rounded-lg shadow-xl w-[480px] p-4 space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between">
          <h2 className="text-sm font-serif text-stone-900">
            Promote {props.sourceBlockIds.length} block
            {props.sourceBlockIds.length === 1 ? "" : "s"} to theme…
          </h2>
          <button
            type="button"
            className="text-stone-400 hover:text-stone-700 text-sm"
            onClick={props.onClose}
            data-testid="promote-close"
            aria-label="Close picker"
          >
            ×
          </button>
        </header>

        <input
          autoFocus
          type="text"
          placeholder="Type a theme name… (existing or new)"
          className={
            "w-full border border-stone-300 rounded-md px-3 py-2 text-sm " +
            "focus:outline-none focus:ring-2 focus:ring-blue-300"
          }
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={submitting}
          data-testid="promote-search"
        />

        {loadStatus === "loading" && (
          <p className="text-xs font-mono text-stone-500">Loading themes…</p>
        )}
        {loadStatus === "unimplemented" && (
          <p className="text-[11px] font-mono text-amber-700">
            Theme API not yet wired on backend; the new-theme path still
            works in spec form. The picker will pull existing themes
            after the route lands.
          </p>
        )}

        {loadStatus !== "loading" && (
          <ul
            className="max-h-64 overflow-y-auto divide-y divide-stone-100 border border-stone-200 rounded-md"
            data-testid="promote-options"
          >
            {filtered.length === 0 && !showCreateOption && (
              <li className="px-3 py-2 text-xs text-stone-500 italic">
                No themes yet — type a title to create one.
              </li>
            )}
            {filtered.map((t) => (
              <li key={t.theme_id}>
                <button
                  type="button"
                  className="w-full text-left px-3 py-2 hover:bg-stone-50 disabled:opacity-50"
                  onClick={() => void promote(t)}
                  disabled={submitting}
                  data-testid={`promote-option-${t.theme_id}`}
                >
                  <div className="text-sm text-stone-900">{t.title}</div>
                  <div className="text-[11px] font-mono text-stone-500">
                    {t.block_count} block{t.block_count === 1 ? "" : "s"}
                  </div>
                </button>
              </li>
            ))}
            {showCreateOption && (
              <li>
                <button
                  type="button"
                  className="w-full text-left px-3 py-2 hover:bg-blue-50 disabled:opacity-50 text-blue-700"
                  onClick={() => void createAndPromote()}
                  disabled={submitting}
                  data-testid="promote-create-new"
                >
                  + New theme: <span className="font-medium">{query.trim()}</span>
                </button>
              </li>
            )}
          </ul>
        )}

        {error && (
          <p className="text-xs font-mono text-red-700" role="alert">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
