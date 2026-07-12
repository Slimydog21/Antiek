import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { track } from "../../lib/analytics";
import {
  appendNotebookBlock,
  deleteNotebookBlock,
  getNotebook,
  patchNotebookBlock,
  reorderNotebookBlocks,
} from "../../lib/api";
import { ArtifactExport } from "../../components/ArtifactExport";
import { fetchTwinNotes } from "../../api/engagement";
import type { TwinNotesResponse } from "../../api/engagement";
import NotebookCanvas from "./NotebookCanvas";
import type {
  NotebookBlockResponse,
  NotebookResponse,
} from "./types";

/**
 * Mode F — Notebook Surface (PostHog Wedge 2 linchpin, master-spec §4.2).
 *
 * TipTap-based literate-analysis document. Substrate references are
 * live-pulled at render time (§13.2 substrate-is-source-of-truth);
 * the notebook stores reference IDs, the renderer resolves the
 * current substrate state on each fetch.
 *
 * Sprint 18-19 ship target. PostHog Wedges 3 (command palette),
 * 4 (ubiquitous AI), and 5 (trajectory replay) all chain off this
 * surface per master-spec §14.3 sequencing discipline.
 */
export default function Notebook() {
  const params = useParams<{ notebookId?: string }>();
  const notebookId = params.notebookId ?? null;
  const [notebook, setNotebook] = useState<NotebookResponse | null>(null);
  const [twinNotes, setTwinNotes] = useState<TwinNotesResponse["notes"]>([]);
  const [twinNotesLoaded, setTwinNotesLoaded] = useState<boolean>(false);
  const loadGeneration = useRef(0);
  const activeNotebookId = useRef<string | null>(notebookId);
  activeNotebookId.current = notebookId;
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const generation = ++loadGeneration.current;
    if (!notebookId) {
      setNotebook(null);
      setTwinNotes([]);
      setTwinNotesLoaded(true);
      return;
    }
    setLoading(true);
    setError(null);
    setNotebook(null);
    setTwinNotes([]);
    setTwinNotesLoaded(false);
    try {
      const data = (await getNotebook(notebookId)) as NotebookResponse;
      if (generation !== loadGeneration.current) return;
      setNotebook(data);
      if (data.document_id) {
        try {
          const twins = await fetchTwinNotes(data.document_id);
          if (generation !== loadGeneration.current) return;
          setTwinNotes(twins.notes || []);
        } catch {
          if (generation !== loadGeneration.current) return;
          setTwinNotes([]);
        } finally {
          if (generation === loadGeneration.current) setTwinNotesLoaded(true);
        }
      } else {
        setTwinNotes([]);
        setTwinNotesLoaded(true);
      }
    } catch (e: unknown) {
      if (generation !== loadGeneration.current) return;
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (generation === loadGeneration.current) setLoading(false);
    }
  }, [notebookId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const appendBlock = useCallback(
    async (req: { block_type: string; content: unknown; ref_id?: string | null }) => {
      if (!notebookId) return;
      const requestedNotebookId = notebookId;
      try {
        const data = (await appendNotebookBlock(notebookId, req)) as NotebookResponse;
        if (activeNotebookId.current !== requestedNotebookId) return;
        track("notebook_block_appended", { block_type: req.block_type });
        setNotebook(data);
      } catch (e: unknown) {
        if (activeNotebookId.current !== requestedNotebookId) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [notebookId],
  );

  const deleteBlock = useCallback(
    async (blockId: string) => {
      if (!notebookId) return;
      const requestedNotebookId = notebookId;
      try {
        const data = (await deleteNotebookBlock(notebookId, blockId)) as NotebookResponse;
        if (activeNotebookId.current !== requestedNotebookId) return;
        track("notebook_block_deleted");
        setNotebook(data);
      } catch (e: unknown) {
        if (activeNotebookId.current !== requestedNotebookId) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [notebookId],
  );

  const editBlock = useCallback(
    async (blockId: string, content: Record<string, unknown>) => {
      if (!notebookId) return;
      const requestedNotebookId = notebookId;
      try {
        const data = (await patchNotebookBlock(
          notebookId, blockId, { content },
        )) as NotebookResponse;
        if (activeNotebookId.current !== requestedNotebookId) return;
        setNotebook(data);
      } catch (e: unknown) {
        if (activeNotebookId.current !== requestedNotebookId) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [notebookId],
  );

  const moveBlock = useCallback(
    async (blockId: string, direction: "up" | "down") => {
      if (!notebookId || !notebook) return;
      const requestedNotebookId = notebookId;
      const sorted = [...notebook.blocks].sort(
        (a, b) => a.block_index - b.block_index,
      );
      const idx = sorted.findIndex((b) => b.block_id === blockId);
      if (idx < 0) return;
      const swapWith = direction === "up" ? idx - 1 : idx + 1;
      if (swapWith < 0 || swapWith >= sorted.length) return;
      const newOrder = sorted.map((b) => b.block_id);
      [newOrder[idx], newOrder[swapWith]] = [newOrder[swapWith], newOrder[idx]];
      try {
        const data = (await reorderNotebookBlocks(
          notebookId, newOrder,
        )) as NotebookResponse;
        if (activeNotebookId.current !== requestedNotebookId) return;
        setNotebook(data);
      } catch (e: unknown) {
        if (activeNotebookId.current !== requestedNotebookId) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [notebookId, notebook],
  );

  if (!notebookId) {
    return <NotebookEmpty />;
  }

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 min-h-0 bg-ice-0 dark:bg-charcoal-2 overflow-y-auto">
        {loading && (
          <div className="px-8 py-6 text-sm text-shadow-1 dark:text-moonlight">Loading notebook…</div>
        )}
        {error && (
          <div className="px-8 py-6 text-sm text-emperor">{error}</div>
        )}
        {notebook && (
          <>
            <div className="px-8 pt-6 flex justify-end">
              <ArtifactExport
                basePath={`/api/notebooks/${notebookId}`}
                filenamePrefix={`notebook-${notebookId}`}
              />
            </div>
            <NotebookCanvas
              notebook={notebook}
              onAppendBlock={appendBlock}
              onDeleteBlock={deleteBlock}
              onMoveBlock={moveBlock}
              onEditBlock={editBlock}
              twinNotes={twinNotes}
              twinNotesLoaded={twinNotesLoaded}
            />
          </>
        )}
      </main>
    </div>
  );
}

function NotebookEmpty() {
  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 flex items-center justify-center bg-ice-0 dark:bg-charcoal-2 px-8 py-12">
        <div className="max-w-md text-center space-y-3">
          <h2 className="text-lg font-serif text-ink dark:text-bright">Notebook</h2>
          <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
            Literate-analysis surface combining region selections,
            claim cards, emergent notes, cross-doc links, prose, and
            LaTeX. Per master-spec §4.2 Sprint 18-19 upgrade.
          </p>
          <p className="text-xs text-shadow-1 dark:text-moonlight italic">
            Notebook needs a notebook_id. Create one via
            POST /notebooks or open one at /notebook/&lt;id&gt;.
          </p>
        </div>
      </main>
    </div>
  );
}

export type { NotebookBlockResponse, NotebookResponse };
