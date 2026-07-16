import { useEffect, useRef, useState } from "react";

import { getChunk } from "../../lib/api";
import type { ChunkResponse } from "../../lib/api";
import { notifyEvidenceSourceOpened } from "../../werner";

/**
 * Modal showing the actual text of a chunk cited by a claim.
 *
 * Fetches /chunks/{id} on open. Shows chunk text + source document
 * title + section_path + tier badge. "Open in document viewer" button
 * deep-links into /wrestle/<doc>?page=N when section_path encodes a
 * page number (PDF source).
 */
export default function ChunkModal({
  chunkId,
  onClose,
  onEvidenceOpened = notifyEvidenceSourceOpened,
}: {
  chunkId: string | null;
  onClose: () => void;
  /** Observes committed readable evidence; Werner-backed and non-authoritative. */
  onEvidenceOpened?: () => void;
}) {
  const [chunk, setChunk] = useState<ChunkResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadedSequence, setLoadedSequence] = useState<number | null>(null);
  const requestSequenceRef = useRef(0);
  const notifiedSequenceRef = useRef<number | null>(null);

  useEffect(() => {
    const sequence = ++requestSequenceRef.current;
    if (!chunkId) {
      setChunk(null);
      setError(null);
      setLoadedSequence(null);
      notifiedSequenceRef.current = null;
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setChunk(null);
    void (async () => {
      try {
        const c = await getChunk(chunkId);
        if (!cancelled) {
          setChunk(c);
          setLoadedSequence(sequence);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chunkId]);

  // This effect runs after React commits the readable chunk. Click intent,
  // loading, withheld content, and stale requests therefore remain silent.
  useEffect(() => {
    if (
      !chunk?.servable ||
      loadedSequence === null ||
      notifiedSequenceRef.current === loadedSequence
    ) {
      return;
    }
    notifiedSequenceRef.current = loadedSequence;
    try {
      onEvidenceOpened();
    } catch {
      // Living-TV choreography observes evidence truth; it never owns the modal.
    }
  }, [chunk, loadedSequence, onEvidenceOpened]);

  // ESC to close.
  useEffect(() => {
    if (!chunkId) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [chunkId, onClose]);

  if (!chunkId) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-ink/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-ice-0 dark:bg-charcoal-2 rounded-lg shadow-xl max-w-2xl w-full max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-3 border-b border-rule dark:border-charcoal-1 flex items-center justify-between">
          <div className="font-mono text-xs text-shadow-1 dark:text-moonlight">
            <code>{chunkId}</code>
          </div>
          <button
            onClick={onClose}
            className="text-ink-mute dark:text-moonlight hover:text-ink dark:text-bright transition-colors text-lg leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading && (
            <div className="text-sm text-ink-mute dark:text-moonlight italic font-serif">
              Loading chunk…
            </div>
          )}
          {error && (
            <div className="text-sm font-mono text-emperor bg-red-50 p-3 rounded">
              {error}
            </div>
          )}
          {chunk && (
            <>
              <div className="mb-3 flex items-center gap-2 flex-wrap text-xs">
                {chunk.document_title && (
                  <span className="font-mono text-ink dark:text-bright">
                    {chunk.document_title}
                  </span>
                )}
                {chunk.section_path && (
                  <span className="font-mono text-shadow-1 dark:text-moonlight">
                    · {chunk.section_path}
                  </span>
                )}
                <TierChip tier={chunk.source_tier} />
              </div>
              {chunk.servable ? (
                <p className="text-sm text-ink dark:text-bright font-serif leading-relaxed whitespace-pre-wrap">
                  {chunk.text}
                </p>
              ) : (
                // §9.0: the endpoint withheld the body for a restricted /
                // taken-down source. Show the honest "not available" state —
                // never the content (it isn't here to show anyway).
                <p className="text-sm text-shadow-1 dark:text-moonlight font-serif italic leading-relaxed">
                  This source isn’t available to open here
                  {chunk.servability === "taken_down"
                    ? " — it was taken down on request."
                    : " — its license restricts the full text."}{" "}
                  You can see what it backs, but not read it inside Antiek.
                </p>
              )}
            </>
          )}
        </div>
        {chunk && (
          <div className="px-5 py-3 border-t border-rule dark:border-charcoal-1 flex items-center justify-between">
            <div className="text-[10px] font-mono text-ink-mute dark:text-moonlight">
              {chunk.servable ? `${chunk.token_count} tokens` : "not available"}
            </div>
            {chunk.servable && <OpenInDocumentButton chunk={chunk} />}
          </div>
        )}
      </div>
    </div>
  );
}

function TierChip({ tier }: { tier: number }) {
  const colorClass =
    tier === 1
      ? "bg-emerald-100 text-emerald-800"
      : tier === 2
        ? "bg-emerald-50 text-emerald-700"
        : tier === 3
          ? "bg-sun/10 text-sun-deep dark:text-sun"
          : "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight";
  return (
    <span
      className={`text-[10px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded ${colorClass}`}
    >
      tier {tier}
    </span>
  );
}

function OpenInDocumentButton({ chunk }: { chunk: ChunkResponse }) {
  // Parse "Page N" out of section_path. Section path examples that
  // encode a page:
  //   "Page 17"
  //   "Page 17 · Section 3.2"
  // When the substrate is extended to YouTube/podcast sources, the
  // section_path uses a different shape (Timestamp: ...) and we
  // disable the cross-mode link.
  let page: number | null = null;
  if (chunk.section_path) {
    const m = chunk.section_path.match(/Page\s+(\d+)/i);
    if (m) page = parseInt(m[1], 10);
  }
  const href =
    page !== null
      ? `/wrestle/${encodeURIComponent(chunk.document_id)}?page=${page}`
      : `/wrestle/${encodeURIComponent(chunk.document_id)}`;
  const label =
    page !== null ? `Open at page ${page}` : "Open in document viewer";
  return (
    <a
      href={href}
      className="text-xs font-mono text-ink dark:text-bright hover:text-ink dark:text-bright px-2 py-1 bg-ice-3 dark:bg-charcoal-1 hover:bg-ice-4 dark:bg-charcoal-1 rounded transition-colors"
    >
      {label} →
    </a>
  );
}
