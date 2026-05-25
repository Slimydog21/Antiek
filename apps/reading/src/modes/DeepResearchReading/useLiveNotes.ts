/**
 * DRW SPR-10 M7 — async notes UX.
 *
 * The notes "take themselves": this hook polls the document's notes + gaps in
 * the background (SPR-03's pass is async, so highlights appear as extraction
 * completes) without blocking reading. Honest pending state: `loading` is true
 * only until the first fetch resolves; thereafter notes stream in on the
 * interval. Matches the codebase's polling idiom (setInterval + cancellation).
 */

import { useEffect, useState } from "react";

import {
  getDocumentGaps,
  getDocumentNotes,
  type DocumentGap,
  type DocumentNote,
} from "../../api/reading";

export interface LiveNotes {
  notes: DocumentNote[];
  gaps: DocumentGap[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useLiveNotes(documentId: string | null, opts: { intervalMs?: number } = {}): LiveNotes {
  const [notes, setNotes] = useState<DocumentNote[]>([]);
  const [gaps, setGaps] = useState<DocumentGap[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!documentId) {
      setNotes([]); setGaps([]); setLoading(false);
      return;
    }
    let cancelled = false;
    const interval = opts.intervalMs ?? 4000;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const [n, g] = await Promise.all([getDocumentNotes(documentId), getDocumentGaps(documentId)]);
        if (cancelled) return;
        setNotes(n.notes);
        setGaps(g.gaps);
        setError(null);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) {
          setLoading(false);
          timer = window.setTimeout(poll, interval);
        }
      }
    };
    void poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId, opts.intervalMs, tick]);

  return { notes, gaps, loading, error, refetch: () => setTick((t) => t + 1) };
}
