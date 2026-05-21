// SPR-11 / M1 + M3 + M5 — Per-theme notebook surface.
//
// Route: /wrestle/themes/:slug
//
// Renders the Tier-3 per-theme notebook: promoted Tier-2 blocks
// interleaved with operator-authored prose framing. Drag-to-reorder
// rewrites sort_order; remove deletes only the theme_blocks row
// (source Tier-2 block untouched); stale placeholders render the
// cached content + a dismiss button.
//
// Save model
// ----------
// Mutations (promote, reorder, remove, prose edit) write through
// the API immediately — no debounced auto-save is needed because
// every operation is structured (one row per click). The Save-as
// menu (M5) exports the current theme state as .antiek, PDF, or
// Markdown.
//
// Persistence-protocol coordination with SPR-09
// ---------------------------------------------
// Native ``.antiek`` save activates automatically when SPR-09 lands.
// We call into services/notebooks/theme_persistence.save_theme_as_antiek
// via the Save-as menu (apps/reading/src/modes/Notebook/SaveAs.tsx);
// the writer body is persistence-agnostic via the SPR-08 Protocol.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  ThemeApiError,
  addProseBlock,
  dismissStaleBlock,
  getThemeBySlug,
  removeThemeBlock,
  reorderThemeBlocks,
  type ThemeResponse,
} from "../../../api/themes/by-slug";
import SaveAs from "./SaveAs";
import ThemeBlockView from "./ThemeBlockView";

export default function PerThemeNotebook(): JSX.Element {
  const params = useParams<{ slug: string }>();
  const slug = params.slug ?? "";

  const [theme, setTheme] = useState<ThemeResponse | null>(null);
  const [status, setStatus] = useState<
    "loading" | "ready" | "error" | "not_found" | "unimplemented"
  >("loading");
  const [error, setError] = useState<string | null>(null);

  // Drag state — which theme_block_id is currently being dragged.
  const dragSourceRef = useRef<string | null>(null);

  const reload = useCallback(async () => {
    if (!slug) {
      setStatus("error");
      setError("No slug in URL");
      return;
    }
    setStatus("loading");
    setError(null);
    try {
      const t = await getThemeBySlug(slug);
      setTheme(t);
      setStatus("ready");
    } catch (err: unknown) {
      if (err instanceof ThemeApiError && err.status === 404) {
        // Two cases: theme doesn't exist, OR backend route not wired.
        // We default to "not_found" — operator clicking through from
        // the index should never hit this since the route is wired
        // together. The first-hit-from-deep-link case shows a banner.
        setStatus("unimplemented");
        return;
      }
      setStatus("error");
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [slug]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // ── Drag-to-reorder ──

  const onDragStart = useCallback((id: string) => {
    dragSourceRef.current = id;
  }, []);
  const onDrop = useCallback(
    async (targetId: string) => {
      if (!theme) return;
      const sourceId = dragSourceRef.current;
      dragSourceRef.current = null;
      if (!sourceId || sourceId === targetId) return;
      const oldOrder = theme.blocks.map((b) => b.theme_block_id);
      const sourceIdx = oldOrder.indexOf(sourceId);
      const targetIdx = oldOrder.indexOf(targetId);
      if (sourceIdx === -1 || targetIdx === -1) return;
      const newOrder = [...oldOrder];
      const [moved] = newOrder.splice(sourceIdx, 1);
      newOrder.splice(targetIdx, 0, moved);
      // Optimistic local update.
      const reindexed = newOrder.map((id, i) => {
        const b = theme.blocks.find((x) => x.theme_block_id === id)!;
        return { ...b, sort_order: i + 1 };
      });
      setTheme({ ...theme, blocks: reindexed });
      try {
        const updated = await reorderThemeBlocks(theme.theme_id, {
          ordered_theme_block_ids: newOrder,
        });
        setTheme(updated);
      } catch (err) {
        // Roll back on failure.
        setTheme(theme);
        // eslint-disable-next-line no-console
        console.warn("[antiek/theme] reorder failed:", err);
      }
    },
    [theme],
  );

  // ── Remove ──

  const onRemove = useCallback(
    async (themeBlockId: string) => {
      if (!theme) return;
      const prev = theme;
      const next: ThemeResponse = {
        ...theme,
        blocks: theme.blocks.filter(
          (b) => b.theme_block_id !== themeBlockId,
        ),
      };
      setTheme(next);
      try {
        await removeThemeBlock(theme.theme_id, themeBlockId);
      } catch (err) {
        setTheme(prev);
        // eslint-disable-next-line no-console
        console.warn("[antiek/theme] remove failed:", err);
      }
    },
    [theme],
  );

  // ── Dismiss stale ──

  const onDismissStale = useCallback(
    async (themeBlockId: string) => {
      if (!theme) return;
      const prev = theme;
      const next: ThemeResponse = {
        ...theme,
        blocks: theme.blocks.filter(
          (b) => b.theme_block_id !== themeBlockId,
        ),
      };
      setTheme(next);
      try {
        await dismissStaleBlock(theme.theme_id, themeBlockId);
      } catch (err) {
        setTheme(prev);
        // eslint-disable-next-line no-console
        console.warn("[antiek/theme] dismiss failed:", err);
      }
    },
    [theme],
  );

  // ── Add prose block ──

  const onAddProse = useCallback(async () => {
    if (!theme) return;
    try {
      const created = await addProseBlock(theme.theme_id, {
        content_json: { text: "" },
      });
      setTheme({ ...theme, blocks: [...theme.blocks, created] });
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("[antiek/theme] add prose failed:", err);
    }
  }, [theme]);

  // ── Cite-jump (delegates to /wrestle/<doc>) ──

  const onCiteJump = useCallback(
    (targetDocumentId: string, targetChunkId?: string | null) => {
      const url =
        `/wrestle/${encodeURIComponent(targetDocumentId)}` +
        (targetChunkId
          ? `?chunk=${encodeURIComponent(targetChunkId)}`
          : "");
      window.location.assign(url);
    },
    [],
  );

  // ── Sorted blocks ──

  const sortedBlocks = useMemo(() => {
    if (!theme) return [];
    return [...theme.blocks].sort((a, b) => a.sort_order - b.sort_order);
  }, [theme]);

  // ── Render ──

  if (status === "loading") {
    return <Shell slug={slug}>Loading theme…</Shell>;
  }
  if (status === "error") {
    return (
      <Shell slug={slug}>
        <p className="text-red-700 text-sm font-mono">
          Failed to load theme: {error}
        </p>
      </Shell>
    );
  }
  if (status === "not_found") {
    return (
      <Shell slug={slug}>
        <p className="text-stone-600 text-sm">
          No theme at <code>/wrestle/themes/{slug}</code>. Did the slug
          change?
        </p>
        <Link
          to="/wrestle/themes"
          className="text-xs font-mono text-blue-700 underline"
        >
          ← back to themes index
        </Link>
      </Shell>
    );
  }
  if (status === "unimplemented" || !theme) {
    return (
      <Shell slug={slug}>
        <p className="text-amber-700 text-xs font-mono">
          Per-theme notebook API is not yet wired on the backend (404
          from GET /api/themes/by-slug/…). The surface is ready; the
          FastAPI route handler lands in a follow-up commit. See
          services/notebooks/theme_persistence.py for the persistence
          contract.
        </p>
      </Shell>
    );
  }

  return (
    <Shell slug={slug} title={theme.title}>
      {theme.cover_snippet && (
        <p className="text-sm font-serif italic text-stone-600 mb-6">
          {theme.cover_snippet}
        </p>
      )}
      {sortedBlocks.length === 0 ? (
        <p
          className="text-stone-500 text-sm italic"
          data-testid="empty-theme"
        >
          Empty theme — promote blocks from any per-doc notebook to
          start building this theme.
        </p>
      ) : (
        <div className="space-y-6 group">
          {sortedBlocks.map((block) => (
            <ThemeBlockView
              key={block.theme_block_id}
              block={block}
              onDragStart={onDragStart}
              onDragOver={() => undefined}
              onDrop={onDrop}
              onRemove={onRemove}
              onDismissStale={onDismissStale}
              onCiteJump={onCiteJump}
              onEditProseContent={() => undefined}
            />
          ))}
        </div>
      )}

      <div className="mt-10 flex items-center gap-3">
        <button
          type="button"
          onClick={() => void onAddProse()}
          className={
            "text-xs font-mono px-3 py-1.5 rounded border border-stone-300 " +
            "bg-white hover:bg-stone-50 text-stone-700"
          }
          data-testid="add-prose-block"
        >
          + add framing
        </button>
        <SaveAs theme={theme} />
      </div>
    </Shell>
  );
}

function Shell({
  slug,
  title,
  children,
}: {
  slug: string;
  title?: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div className="flex flex-col h-screen bg-stone-50">
      <header className="flex items-center justify-between px-6 py-3 border-b border-stone-200 bg-white">
        <div className="flex items-center gap-3">
          <Link
            to="/wrestle/themes"
            className="text-xs font-mono text-stone-500 hover:text-stone-900"
            data-testid="back-to-themes-index"
          >
            ← all themes
          </Link>
          <h1 className="text-sm font-serif text-stone-900">
            {title || "Theme"}
          </h1>
        </div>
        <span className="text-[11px] font-mono text-stone-400">{slug}</span>
      </header>
      <main className="flex-1 overflow-y-auto">
        <article className="max-w-3xl mx-auto px-8 py-10">{children}</article>
      </main>
    </div>
  );
}
