import { useCallback, useEffect, useState } from "react";

import {
  createAnchor,
  deleteAnchor,
  listAnchors,
  ApiError,
  type BookAnchor,
} from "../lib/api";

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
  const [anchors, setAnchors] = useState<BookAnchor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (!documentId) {
      setAnchors([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const resp = await listAnchors(documentId);
        if (!cancelled) {
          setAnchors(resp.anchors);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setAnchors([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [documentId, tick]);

  const pin = useCallback(
    async (body: {
      quote?: string;
      prefix?: string;
      suffix?: string;
      page_index_hint?: number;
      source?: string;
    }): Promise<BookAnchor> => {
      if (!documentId) throw new ApiError("useAnchors.pin without a document", 0, "");
      const anchor = await createAnchor(documentId, body);
      refetch();
      return anchor;
    },
    [documentId, refetch],
  );

  const remove = useCallback(
    async (anchorId: string): Promise<void> => {
      if (!documentId) return;
      await deleteAnchor(documentId, anchorId);
      refetch();
    },
    [documentId, refetch],
  );

  return { anchors, loading, error, refetch, pin, remove };
}
