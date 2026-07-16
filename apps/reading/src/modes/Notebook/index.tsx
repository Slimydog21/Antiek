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
import NotebookCanvas from "./NotebookCanvas";
import type {
  NotebookBlockResponse,
  NotebookResponse,
  NotebookSurfaceProps,
} from "./types";

import "./recursive-fieldbook.css";

/**
 * Mode F — Notebook Surface (PostHog Wedge 2 linchpin, master-spec §4.2).
 *
 * Ordered-block fieldbook with honest cached-reference/tombstone authority.
 * References are visibly identified by type and reference ID; cached text
 * is never called resolved/live. No twin generation, no graph resolution.
 *
 * Stale route suppression: a sequence counter ensures a late prior-route
 * GET cannot replace a newer notebook after navigation or unmount.
 *
 * Mutation serialization: one explicit mutation lane prevents overlapping
 * snapshots from overwriting newer notebook state. On failure, the last
 * confirmed notebook remains rendered.
 */

/** Fixed safe error copy — no URL, HTTP status, response body, stack, or secret. */
function safeErrorMessage(action: string): string {
  return `Could not ${action} the block. Your notebook is unchanged.`;
}

export default function Notebook({
  notebookIdOverride,
  initialNotebook = null,
  initialLoading = false,
  initialError = null,
  executionEnabled = true,
  initialMutationPending = false,
}: Partial<NotebookSurfaceProps> = {}) {
  const params = useParams<{ notebookId?: string }>();
  const notebookId = notebookIdOverride !== undefined
    ? notebookIdOverride
    : params.notebookId ?? null;

  const [notebook, setNotebook] = useState<NotebookResponse | null>(initialNotebook);
  const [loading, setLoading] = useState<boolean>(initialLoading);
  const [error, setError] = useState<string | null>(initialError);
  const [mutationPending, setMutationPending] = useState<boolean>(initialMutationPending);

  // Stale route suppression: monotonically increasing sequence. Each new
  // notebookId bumps the seq; unmount resets to 0. A late prior-route GET
  // that resolves after the seq has advanced is silently discarded.
  const seqRef = useRef(0);
  // Mutation serialization: one-at-a-time lane. The next mutation waits
  // for the current one to resolve before starting.
  const mutationQueueRef = useRef<Promise<void>>(Promise.resolve());
  // Track the action class of the in-flight mutation for safe error copy.
  const lastActionRef = useRef<string>("mutate");

  useEffect(() => {
    const currentSeq = ++seqRef.current;
    if (!executionEnabled) {
      setNotebook(initialNotebook);
      setLoading(initialLoading);
      setError(initialError);
      setMutationPending(initialMutationPending);
      return;
    }
    if (!notebookId) {
      setNotebook(null);
      setLoading(false);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);

    void getNotebook(notebookId)
      .then((data) => {
        // Suppress stale route: a prior notebookId's late response.
        if (seqRef.current !== currentSeq) return;
        if (!isNotebookResponse(data)) throw new Error("invalid notebook response");
        setNotebook(data);
      })
      .catch(() => {
        if (seqRef.current !== currentSeq) return;
        setError("Could not load notebook. Please try again.");
      })
      .finally(() => {
        if (seqRef.current !== currentSeq) return;
        setLoading(false);
      });
  }, [executionEnabled, initialError, initialLoading, initialMutationPending, initialNotebook, notebookId]);

  // Reset stale-route counter on unmount.
  useEffect(() => {
    return () => {
      seqRef.current = 0;
    };
  }, []);

  /**
   * Serialize a mutation through the single-flight lane.
   * While a mutation is pending, conflicting controls are disabled
   * (via mutationPending prop to NotebookCanvas). On failure, the
   * last confirmed notebook remains rendered and a safe error is shown.
   */
  const enqueueMutation = useCallback(
    (action: string, fn: () => Promise<unknown>, onSuccess?: () => void) => {
      const mutationNotebookId = notebookId;
      const mutationSeq = seqRef.current;
      const next = mutationQueueRef.current.then(async () => {
        if (!executionEnabled || !mutationNotebookId) return;
        if (seqRef.current !== mutationSeq) return;
        setMutationPending(true);
        lastActionRef.current = action;
        try {
          const data = await fn();
          if (!isNotebookResponse(data)) throw new Error("invalid notebook response");
          if (seqRef.current !== mutationSeq) return;
          setNotebook(data);
          setError(null);
          try {
            onSuccess?.();
          } catch {
            // Telemetry is best-effort and must never rewrite mutation truth.
          }
        } catch {
          // Safe fixed error: no URL, no HTTP status, no stack, no secret.
          // The last confirmed notebook remains rendered.
          if (seqRef.current === mutationSeq) setError(safeErrorMessage(action));
        } finally {
          if (seqRef.current === mutationSeq) setMutationPending(false);
        }
      });
      // Chain: the next queued mutation waits for this one.
      mutationQueueRef.current = next.then(() => undefined);
    },
    [executionEnabled, notebookId],
  );

  const appendBlock = useCallback(
    (req: { block_type: string; content: unknown; ref_id?: string | null }) => {
      if (!notebookId) return;
      enqueueMutation(
        "append",
        () => appendNotebookBlock(notebookId, req),
        () => track("notebook_block_appended", { block_type: req.block_type }),
      );
    },
    [notebookId, enqueueMutation],
  );

  const deleteBlock = useCallback(
    (blockId: string) => {
      if (!notebookId) return;
      enqueueMutation(
        "delete",
        () => deleteNotebookBlock(notebookId, blockId),
        () => track("notebook_block_deleted"),
      );
    },
    [notebookId, enqueueMutation],
  );

  const editBlock = useCallback(
    (blockId: string, content: Record<string, unknown>) => {
      if (!notebookId) return;
      enqueueMutation("edit", () =>
        patchNotebookBlock(notebookId, blockId, { content }),
      );
    },
    [notebookId, enqueueMutation],
  );

  const moveBlock = useCallback(
    (blockId: string, direction: "up" | "down") => {
      if (!notebookId || !notebook) return;
      const sorted = [...notebook.blocks].sort(
        (a, b) => a.block_index - b.block_index,
      );
      const idx = sorted.findIndex((b) => b.block_id === blockId);
      if (idx < 0) return;
      const swapWith = direction === "up" ? idx - 1 : idx + 1;
      if (swapWith < 0 || swapWith >= sorted.length) return;
      const newOrder = sorted.map((b) => b.block_id);
      [newOrder[idx], newOrder[swapWith]] = [newOrder[swapWith], newOrder[idx]];
      enqueueMutation("reorder", () =>
        reorderNotebookBlocks(notebookId, newOrder),
      );
    },
    [notebookId, notebook, enqueueMutation],
  );

  if (!notebookId) {
    return <NotebookMissingId />;
  }

  return (
    <div className="recursive-fieldbook flex flex-col h-screen">
      <main className="flex-1 min-h-0 bg-ice-0 dark:bg-charcoal-2 overflow-y-auto">
        {loading && (
          <div className="px-8 py-6 text-sm text-shadow-1 dark:text-moonlight">
            Loading notebook…
          </div>
        )}
        {error && (
          <div
            role="alert"
            className="px-8 py-6 text-sm text-emperor"
          >
            {error}
          </div>
        )}
        {notebook && (
          <>
            {executionEnabled && <div className="px-8 pt-6 flex justify-end">
              <ArtifactExport
                basePath={`/api/notebooks/${notebookId}`}
                filenamePrefix={`notebook-${notebookId}`}
              />
            </div>}
            <NotebookCanvas
              notebook={notebook}
              onAppendBlock={appendBlock}
              onDeleteBlock={deleteBlock}
              onMoveBlock={moveBlock}
              onEditBlock={editBlock}
              mutationPending={mutationPending}
            />
          </>
        )}
      </main>
    </div>
  );
}

/** Missing notebook ID — honest navigation guidance, no POST instructions. */
function NotebookMissingId() {
  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 flex items-center justify-center bg-ice-0 dark:bg-charcoal-2 px-8 py-12">
        <div className="max-w-md text-center space-y-3">
          <h2 className="text-lg font-serif text-ink dark:text-bright">
            Notebook
          </h2>
          <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
            Open a notebook to see its blocks here.
          </p>
        </div>
      </main>
    </div>
  );
}

export type { NotebookBlockResponse, NotebookResponse, NotebookSurfaceProps };

function isNotebookResponse(value: unknown): value is NotebookResponse {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<NotebookResponse>;
  const allowedTypes = new Set([
    "prose", "region_embed", "claim_card", "note", "question_card",
    "cross_doc_link", "chat_exchange", "master_md_section", "image", "latex",
  ]);
  return typeof candidate.notebook_id === "string"
    && typeof candidate.title === "string"
    && (candidate.content_class === "user_owned" || candidate.content_class === "user_public_contribution")
    && typeof candidate.updated_at === "string"
    && Array.isArray(candidate.blocks)
    && candidate.blocks.every((block) => Boolean(block)
      && typeof block.block_id === "string"
      && Number.isInteger(block.block_index)
      && allowedTypes.has(block.block_type)
      && (block.ref_id === null || typeof block.ref_id === "string")
      && Boolean(block.content_json)
      && typeof block.content_json === "object"
      && !Array.isArray(block.content_json)
      && typeof block.created_at === "string");
}
