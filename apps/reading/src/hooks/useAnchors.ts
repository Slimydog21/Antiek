import { useCallback, useEffect, useState } from "react";

import {
  createAnchor,
  deleteAnchor,
  listAnchors,
  ApiError,
  type BookAnchor,
} from "../lib/api";
import {
  isWorkspaceOwnerSession,
  useWorkspaceOwner,
  type WorkspaceOwnerSession,
} from "../lib/accountWorkspaceOwner";

export interface UseAnchorsState {
  anchors: BookAnchor[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
  /** Pin a passage (the server resolves the unique chunk + offsets), then
   *  refetch so the list reflects the stored row. Returns the stored anchor. */
  pin: (body: {
    quote?: string;
    prefix?: string;
    suffix?: string;
    page_index_hint?: number;
    source?: string;
  }) => Promise<BookAnchor>;
  /** Idempotent server-side (second delete is a 204); refetches after. */
  remove: (anchorId: string) => Promise<void>;
}

/**
 * The owner's anchored highlights for one document (anchor-first SPR-03).
 * Follows the useInvestigationList conventions: load on mount (once per
 * document id), expose loading/error, and refetch after every mutation —
 * no polling; the anchors only change through this client's pins/deletes or
 * a server-side re-resolution the next load reports.
 */
export function useAnchors(documentId: string | null): UseAnchorsState {
  const owner = useWorkspaceOwner();
  const [frame, setFrame] = useState<{
    owner: WorkspaceOwnerSession;
    documentId: string | null;
    anchors: BookAnchor[];
    loading: boolean;
    error: string | null;
  }>(() => ({ owner, documentId, anchors: [], loading: true, error: null }));
  const [tick, setTick] = useState(0);

  const refetch = useCallback(() => {
    if (owner.subject !== null && isWorkspaceOwnerSession(owner)) setTick((t) => t + 1);
  }, [owner]);

  useEffect(() => {
    if (!documentId || owner.subject === null) {
      setFrame({ owner, documentId, anchors: [], loading: false, error: null });
      return;
    }
    let cancelled = false;
    const current = () => !cancelled && isWorkspaceOwnerSession(owner);
    setFrame((previous) => ({
      owner, documentId, loading: true, error: null,
      anchors: previous.owner === owner && previous.documentId === documentId ? previous.anchors : [],
    }));
    void (async () => {
      try {
        const resp = await listAnchors(documentId);
        if (current()) setFrame({ owner, documentId, anchors: resp.anchors, loading: false, error: null });
      } catch (e) {
        if (current()) {
          setFrame({
            owner, documentId, anchors: [], loading: false,
            error: e instanceof Error ? e.message : String(e),
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [documentId, tick, owner]);

  const pin = useCallback(
    async (body: {
      quote?: string;
      prefix?: string;
      suffix?: string;
      page_index_hint?: number;
      source?: string;
    }): Promise<BookAnchor> => {
      if (!documentId) throw new ApiError("useAnchors.pin without a document", 0, "");
      if (owner.subject === null || !isWorkspaceOwnerSession(owner)) {
        throw new ApiError("Account changed before the passage could be saved.", 409, "");
      }
      const anchor = await createAnchor(documentId, body);
      if (!isWorkspaceOwnerSession(owner)) {
        throw new ApiError("Account changed before the passage could be saved.", 409, "");
      }
      refetch();
      return anchor;
    },
    [documentId, refetch, owner],
  );

  const remove = useCallback(
    async (anchorId: string): Promise<void> => {
      if (!documentId) return;
      if (owner.subject === null || !isWorkspaceOwnerSession(owner)) return;
      await deleteAnchor(documentId, anchorId);
      if (!isWorkspaceOwnerSession(owner)) return;
      refetch();
    },
    [documentId, refetch, owner],
  );

  const current = frame.owner === owner && frame.documentId === documentId && owner.subject !== null;
  return {
    anchors: current ? frame.anchors : [],
    loading: current ? frame.loading : documentId !== null && owner.subject !== null,
    error: current ? frame.error : null,
    refetch, pin, remove,
  };
}
