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
      <div className="space-y-4">
        {visibleBlocks.map((block) =>
          renderBlock({
            block,
            onCiteJump,
            onDemote,
            onEditFraming,
          }),
        )}
      </div>
      <DemoteZone
        blocks={demotedBlocks}
        onDemote={onDemote}
        onCiteJump={onCiteJump}
        onEditFraming={onEditFraming}
      />
    </Shell>
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
