import { useEffect, useRef, useState } from "react";

import { ErrorBanner } from "../../components/lemon/ErrorBanner";
import { LemonModal } from "../../components/lemon/LemonModal";
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

  if (!chunkId) return null;

  return (
    <LemonModal
      open
      onClose={onClose}
      size="md"
      title={<code className="normal-case tracking-normal">{chunkId}</code>}
      footer={
        chunk ? (
          <div className="flex items-center justify-between">
            <div className="text-xxs font-mono text-ink-mute dark:text-moonlight">
              {chunk.servable ? `${chunk.token_count} tokens` : "not available"}
            </div>
            {chunk.servable && <OpenInDocumentButton chunk={chunk} />}
          </div>
        ) : undefined
      }
    >
      <div className="max-h-[65vh] overflow-y-auto">
        {loading && (
          <div className="text-sm text-ink-mute dark:text-moonlight italic font-serif">
            Loading chunk…
          </div>
        )}
        {error && (
          <ErrorBanner className="font-mono">
            {error}
          </ErrorBanner>
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
    </LemonModal>
  );
}

function TierChip({ tier }: { tier: number }) {
  const colorClass =
    tier === 1
      ? "bg-success/15 text-success"
      : tier === 2
        ? "bg-success/10 text-success"
        : tier === 3
          ? "bg-sun/10 text-sun-deep dark:text-sun"
          : "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight";
  return (
    <span
      className={`text-xxs font-mono uppercase tracking-wide px-1.5 py-0.5 rounded ${colorClass}`}
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
