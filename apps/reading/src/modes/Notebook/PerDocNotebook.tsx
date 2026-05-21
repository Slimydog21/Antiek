// SPR-08 / M1 + M4 + M5 + M6 — Per-document notebook surface.
//
// Route: /wrestle/:documentId/notebook
//
// Lifecycle
// ---------
// 1. Mount: GET /api/notebooks/by-doc/:documentId. The server auto-
//    populates from Tier-1 events on first hit (services/notebooks/
//    auto_populate.py). 404 means the route handler isn't shipped
//    yet; we render the empty state + a banner instead of crashing.
//
// 2. Render: blocks split into "visible" + "demoted (N)". Demoted
//    collapsed by default; the user can expand + restore.
//
// 3. Edit framing: per-block textarea on the BlockShell footer.
//    onBlur fires editPerDocBlock which bumps edited_at and emits
//    notebook_block_edited.
//
// 4. Demote: per-block button. Flips demoted_at, emits
//    notebook_block_demoted.
//
// 5. Save: debounced 2s auto-save + Cmd+S explicit. The save body
//    carries the TipTap document JSON + the structured block list;
//    the server's persistence.JSONPersistence is the writer.
//
// What's NOT here
// ---------------
// - No "+ new block" affordance. See services/notebooks/
//   BLOCK_TAXONOMY.md "Why no + new block". An operator who wants
//   to author free text uses the per-block framing textarea.
//
// - No session-scoped logic. The notebook is keyed on document_id
//   only; sessions live in the behavior store and are not surfaced
//   here.

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  PerDocNotebookError,
  editPerDocBlock,
  getPerDocNotebook,
  savePerDocNotebook,
  toggleDemoteBlock,
  type PerDocNotebookBlock,
  type PerDocNotebookResponse,
} from "../../../api/notebooks/by-doc";
import { renderBlock } from "./blocks";
import DemoteZone from "./DemoteZone";
import PromoteToTheme from "./PromoteToTheme";
import {
  BehaviorEventType,
  emitBehaviorEvent,
} from "../../lib/behaviorEvents";

const AUTO_SAVE_DEBOUNCE_MS = 2000;

export default function PerDocNotebook(): JSX.Element {
  const params = useParams<{ documentId: string }>();
  const documentId = params.documentId ?? "";

  const [notebook, setNotebook] = useState<PerDocNotebookResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error" | "unimplemented">(
    "loading",
  );
  const [error, setError] = useState<string | null>(null);
  const [pendingSave, setPendingSave] = useState<number>(0);

  // SPR-11 / M2 — promote-to-theme selection state.
  //
  // ``selectedBlockIds`` is the multi-select set the operator builds
  // by Shift-clicking the promote affordance on multiple blocks; it
  // is also the single-element case when the operator clicks one
  // block's affordance directly. ``promotePickerOpen`` flips when
  // the operator confirms; the picker modal opens with the current
  // selection.
  //
  // ``promotedIndicator`` records the last theme each block landed
  // in so the "in theme: <title>" indicator appears immediately
  // post-promote without a full reload. The persistence-backed
  // version of this lookup is GET /api/themes/by-source-block/<id>;
  // this in-memory cache is the optimistic mirror.
  const [selectedBlockIds, setSelectedBlockIds] = useState<Set<string>>(
    new Set(),
  );
  const [promotePickerOpen, setPromotePickerOpen] = useState(false);
  const [promotedIndicator, setPromotedIndicator] = useState<
    Record<string, { themeId: string; themeTitle: string }>
  >({});

  // ── Load on mount + when documentId changes ──

  useEffect(() => {
    let cancelled = false;
    if (!documentId) {
      setStatus("error");
      setError("No documentId in URL");
      return;
    }
    setStatus("loading");
    setError(null);
    void getPerDocNotebook(documentId)
      .then((nb) => {
        if (cancelled) return;
        setNotebook(nb);
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof PerDocNotebookError && err.status === 404) {
          // FastAPI route not yet wired — render empty state with banner.
          setStatus("unimplemented");
          return;
        }
        setStatus("error");
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  // ── Debounced auto-save ──
  //
  // Whenever the operator edits framing or reorders, we bump
  // pendingSave; a 2s timer flushes the current notebook to the
  // server. Cmd+S short-circuits to an explicit save immediately.

  useEffect(() => {
    if (!notebook || pendingSave === 0) return;
    const handle = window.setTimeout(() => {
      void persistSave(notebook, "auto");
    }, AUTO_SAVE_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingSave]);

  const persistSave = useCallback(
    async (current: PerDocNotebookResponse, kind: "auto" | "explicit") => {
      try {
        const updated = await savePerDocNotebook(documentId, {
          notebook_id: current.notebook_id,
          content_json: current.content_json,
          blocks: current.blocks,
          save_kind: kind,
        });
        setNotebook(updated);
      } catch (err) {
        // Save failures are non-fatal — operator can retry with Cmd+S.
        // eslint-disable-next-line no-console
        console.warn("[antiek/notebook] save failed:", err);
      }
    },
    [documentId],
  );

  // ── Cmd+S explicit save ──

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        if (notebook) void persistSave(notebook, "explicit");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [notebook, persistSave]);

  // ── Block handlers ──

  const onDemote = useCallback(
    (blockId: string, demoted: boolean) => {
      if (!notebook) return;
      // Optimistic local update so the UI feels live.
      const now = new Date().toISOString();
      const next: PerDocNotebookResponse = {
        ...notebook,
        blocks: notebook.blocks.map((b) =>
          b.block_id === blockId
            ? { ...b, demoted_at: demoted ? now : null }
            : b,
        ),
      };
      setNotebook(next);
      // Emit the Tier-1 behavior event so the reward proxy sees the
      // demote. Pre-API-wire this is a no-op-on-the-wire (see
      // apps/reading/src/lib/behaviorEvents.ts); the call site is
      // correct from day one.
      const block = notebook.blocks.find((b) => b.block_id === blockId);
      if (block && demoted) {
        emitBehaviorEvent({
          eventType: BehaviorEventType.NOTEBOOK_BLOCK_DEMOTED,
          state: {
            notebook_id: notebook.notebook_id,
            block_id: blockId,
            from_tier: 2,
            document_id: notebook.document_id,
          },
          action: { to_tier: 1, reason: null },
          documentId: notebook.document_id,
        });
      }
      // Server-side flip.
      void toggleDemoteBlock(documentId, blockId, demoted).catch((err) => {
        // eslint-disable-next-line no-console
        console.warn("[antiek/notebook] demote toggle failed:", err);
      });
    },
    [documentId, notebook],
  );

  const onEditFraming = useCallback(
    (blockId: string, framing: string) => {
      if (!notebook) return;
      const block = notebook.blocks.find((b) => b.block_id === blockId);
      if (!block) return;
      const nextContent = {
        ...(block.content_json as Record<string, unknown>),
        operator_framing: framing,
      };
      // Optimistic.
      const next: PerDocNotebookResponse = {
        ...notebook,
        blocks: notebook.blocks.map((b) =>
          b.block_id === blockId ? { ...b, content_json: nextContent } : b,
        ),
      };
      setNotebook(next);
      setPendingSave((n) => n + 1);
      emitBehaviorEvent({
        eventType: BehaviorEventType.NOTEBOOK_BLOCK_EDITED,
        state: {
          notebook_id: notebook.notebook_id,
          block_id: blockId,
          tier: 2,
          document_id: notebook.document_id,
        },
        action: {
          edit_kind: "framing",
          chars_added: framing.length,
          chars_removed: null,
        },
        documentId: notebook.document_id,
      });
      // Server-side patch.
      void editPerDocBlock(documentId, blockId, nextContent).catch((err) => {
        // eslint-disable-next-line no-console
        console.warn("[antiek/notebook] edit framing failed:", err);
      });
    },
    [documentId, notebook],
  );

  const onCiteJump = useCallback(
    (targetDocumentId: string, targetChunkId?: string | null) => {
      // Sprint 18 deep-link convention: ?page is the PDF page (when
      // available) but cite-jumps generally use ?chunk= which the
      // WrestleApp's PdfViewer resolves. We delegate to the existing
      // route + query string — same path SPR-07 uses.
      const url =
        `/wrestle/${encodeURIComponent(targetDocumentId)}` +
        (targetChunkId
          ? `?chunk=${encodeURIComponent(targetChunkId)}`
          : "");
      window.location.assign(url);
    },
    [],
  );

  // ── Split into visible + demoted ──

  const { visibleBlocks, demotedBlocks } = useMemo(() => {
    if (!notebook) {
      return { visibleBlocks: [], demotedBlocks: [] };
    }
    const visible: PerDocNotebookBlock[] = [];
    const demoted: PerDocNotebookBlock[] = [];
    for (const b of [...notebook.blocks].sort(
      (a, b) => a.position - b.position,
    )) {
      (b.demoted_at !== null ? demoted : visible).push(b);
    }
    return { visibleBlocks: visible, demotedBlocks: demoted };
  }, [notebook]);

  // ── Render ──

  if (status === "loading") {
    return <Shell documentId={documentId}>Loading notebook…</Shell>;
  }
  if (status === "error") {
    return (
      <Shell documentId={documentId}>
        <p className="text-red-700 text-sm font-mono">
          Failed to load notebook: {error}
        </p>
      </Shell>
    );
  }
  if (status === "unimplemented" || !notebook) {
    return (
      <Shell documentId={documentId}>
        <div className="space-y-3">
          <p className="text-amber-700 text-xs font-mono">
            Per-doc notebook API is not yet wired on the backend (404 from
            GET /api/notebooks/by-doc/…). The surface is ready; the
            FastAPI route handler lands in a follow-up commit. See
            services/notebooks/auto_populate.py for the populator and
            apps/reading/api/notebooks/by-doc.ts for the contract.
          </p>
          <p className="text-stone-500 text-sm italic">
            Empty notebook — no events on this document yet.
          </p>
        </div>
      </Shell>
    );
  }

  return (
    <Shell documentId={documentId} title={notebook.title}>
      {visibleBlocks.length === 0 && demotedBlocks.length === 0 && (
        <p
          className="text-stone-500 text-sm italic"
          data-testid="empty-notebook"
        >
          Empty notebook — no events on this document yet.
        </p>
      )}
      {/* SPR-11 / M2 — promote toolbar visible whenever there's a
        selection. The single-block path goes through onPromoteOne;
        the multi-block path uses this batch toolbar. */}
      {selectedBlockIds.size > 0 && (
        <div
          className="sticky top-0 z-10 flex items-center justify-between mb-3 px-3 py-2 bg-stone-900 text-white rounded-md shadow-md"
          data-testid="promote-toolbar"
        >
          <span className="text-xs font-mono">
            {selectedBlockIds.size} selected
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="text-xs font-mono px-2 py-1 rounded bg-white text-stone-900 hover:bg-stone-100"
              onClick={() => setPromotePickerOpen(true)}
              data-testid="promote-toolbar-submit"
            >
              Promote to theme…
            </button>
            <button
              type="button"
              className="text-xs font-mono px-2 py-1 rounded text-stone-300 hover:text-white"
              onClick={() => setSelectedBlockIds(new Set())}
              data-testid="promote-toolbar-clear"
            >
              clear
            </button>
          </div>
        </div>
      )}

      <div className="space-y-4">
        {visibleBlocks.map((block) => (
          <BlockWithPromote
            key={block.block_id}
            block={block}
            selected={selectedBlockIds.has(block.block_id)}
            inTheme={promotedIndicator[block.block_id] ?? null}
            onToggleSelect={(id, additive) =>
              setSelectedBlockIds((prev) => {
                const next = new Set(additive ? prev : []);
                if (next.has(id)) next.delete(id);
                else next.add(id);
                return next;
              })
            }
            onPromoteOne={(id) => {
              setSelectedBlockIds(new Set([id]));
              setPromotePickerOpen(true);
            }}
          >
            {renderBlock({
              block,
              onCiteJump,
              onDemote,
              onEditFraming,
            })}
          </BlockWithPromote>
        ))}
      </div>
      <DemoteZone
        blocks={demotedBlocks}
        onDemote={onDemote}
        onCiteJump={onCiteJump}
        onEditFraming={onEditFraming}
      />

      {/* SPR-11 / M2 — picker modal. Mounts only when needed. */}
      {promotePickerOpen && (
        <PromoteToTheme
          sourceBlockIds={Array.from(selectedBlockIds)}
          onClose={() => setPromotePickerOpen(false)}
          onPromoted={(themeId, themeTitle) => {
            // Stamp the "in theme: <title>" indicator on each
            // promoted block immediately.
            const promoted = Array.from(selectedBlockIds);
            setPromotedIndicator((prev) => {
              const next = { ...prev };
              for (const id of promoted) {
                next[id] = { themeId, themeTitle };
              }
              return next;
            });
            // Taxonomy v2 (2026-05-22): notebook_block_promoted is
            // now in the closed taxonomy. emitBehaviorEvent is sync;
            // wrap in try/catch so emit failures are non-fatal.
            // One emit per promoted block so the reward proxy can
            // join per-block.
            for (const blockId of promoted) {
              const sourceBlock = notebook?.blocks.find(
                (b) => b.block_id === blockId,
              );
              try {
                emitBehaviorEvent({
                  eventType: BehaviorEventType.NOTEBOOK_BLOCK_PROMOTED,
                  state: {
                    source_notebook_id: notebook?.notebook_id ?? "unknown",
                    source_block_id: blockId,
                    source_document_id: documentId ?? null,
                    block_type: sourceBlock?.block_type ?? null,
                  },
                  action: {
                    theme_id: themeId,
                    theme_slug: null,
                    theme_block_id: null,
                    newly_created_theme: null,
                  },
                });
              } catch {
                // Swallow — emit failure is non-fatal.
              }
            }
            setSelectedBlockIds(new Set());
            setPromotePickerOpen(false);
          }}
        />
      )}
    </Shell>
  );
}

/** Wraps a Tier-2 block render with the SPR-11 promote affordance
 *  and the "in theme: <title>" indicator. The wrapper is its own
 *  component so the existing renderBlock dispatch (used by both
 *  Tier-2 and Tier-3 surfaces) stays untouched.
 */
function BlockWithPromote({
  block,
  selected,
  inTheme,
  onToggleSelect,
  onPromoteOne,
  children,
}: {
  block: PerDocNotebookBlock;
  selected: boolean;
  inTheme: { themeId: string; themeTitle: string } | null;
  onToggleSelect: (id: string, additive: boolean) => void;
  onPromoteOne: (id: string) => void;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div
      className={
        "relative " + (selected ? "ring-2 ring-blue-400 rounded-md" : "")
      }
      data-promote-host={block.block_id}
    >
      {children}
      <div className="mt-1 flex items-center justify-between text-[11px] font-mono text-stone-500">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onPromoteOne(block.block_id)}
            className="hover:text-stone-900 underline-offset-2 hover:underline"
            data-testid={`promote-button-${block.block_id}`}
            title="Promote this block to a theme"
          >
            ↗ Promote to theme…
          </button>
          <label className="inline-flex items-center gap-1 cursor-pointer">
            <input
              type="checkbox"
              checked={selected}
              onChange={() =>
                // Multi-select is always-on for the checkbox row; shift-
                // click range-select is a deferred follow-up (the
                // original `e.shiftKey || true` always evaluated to
                // true because ChangeEvent has no shiftKey).
                onToggleSelect(block.block_id, true)
              }
              data-testid={`promote-select-${block.block_id}`}
              className="cursor-pointer"
            />
            <span className="text-stone-400">multi-select</span>
          </label>
        </div>
        {inTheme && (
          <span
            className="text-stone-600"
            data-testid={`in-theme-indicator-${block.block_id}`}
          >
            in theme: <strong>{inTheme.themeTitle}</strong>
          </span>
        )}
      </div>
    </div>
  );
}

// ── Shell ──

function Shell({
  documentId,
  title,
  children,
}: {
  documentId: string;
  title?: string | null;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div className="flex flex-col h-screen bg-stone-50">
      <header className="flex items-center justify-between px-6 py-3 border-b border-stone-200 bg-white">
        <div className="flex items-center gap-3">
          <Link
            to={`/wrestle/${encodeURIComponent(documentId)}`}
            className="text-xs font-mono text-stone-500 hover:text-stone-900"
            data-testid="back-to-pdf"
          >
            ← back to PDF
          </Link>
          <h1 className="text-sm font-serif text-stone-900">
            {title || "Per-document notebook"}
          </h1>
        </div>
        <span className="text-[11px] font-mono text-stone-400">
          {documentId.slice(-12)}
        </span>
      </header>
      <main className="flex-1 overflow-y-auto">
        <article className="max-w-3xl mx-auto px-8 py-10">{children}</article>
      </main>
    </div>
  );
}
