import { useEffect, useState } from "react";

import { getChunk } from "../../lib/api";
import type { ChunkResponse } from "../../lib/api";

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
}: {
  chunkId: string | null;
  onClose: () => void;
}) {
  const [chunk, setChunk] = useState<ChunkResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!chunkId) {
      setChunk(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setChunk(null);
    void (async () => {
      try {
        const c = await getChunk(chunkId);
        if (!cancelled) setChunk(c);
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
      className="fixed inset-0 z-50 bg-stone-900/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-3 border-b border-stone-200 flex items-center justify-between">
          <div className="font-mono text-xs text-stone-500">
            <code>{chunkId}</code>
          </div>
          <button
            onClick={onClose}
            className="text-stone-400 hover:text-stone-900 transition-colors text-lg leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading && (
            <div className="text-sm text-stone-400 italic font-serif">
              Loading chunk…
            </div>
          )}
          {error && (
            <div className="text-sm font-mono text-red-700 bg-red-50 p-3 rounded">
              {error}
            </div>
          )}
          {chunk && (
            <>
              <div className="mb-3 flex items-center gap-2 flex-wrap text-xs">
                {chunk.document_title && (
                  <span className="font-mono text-stone-700">
                    {chunk.document_title}
                  </span>
                )}
                {chunk.section_path && (
                  <span className="font-mono text-stone-500">
                    · {chunk.section_path}
                  </span>
                )}
                <TierChip tier={chunk.source_tier} />
              </div>
              <p className="text-sm text-stone-900 font-serif leading-relaxed whitespace-pre-wrap">
                {chunk.text}
              </p>
            </>
          )}
        </div>
        {chunk && (
          <div className="px-5 py-3 border-t border-stone-200 flex items-center justify-between">
            <div className="text-[10px] font-mono text-stone-400">
              {chunk.token_count} tokens
            </div>
            <OpenInDocumentButton chunk={chunk} />
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
          ? "bg-amber-50 text-amber-700"
          : "bg-stone-100 text-stone-600";
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
  const label = page !== null ? `Open at page ${page}` : "Open in document viewer";
  return (
    <a
      href={href}
      className="text-xs font-mono text-stone-700 hover:text-stone-900 px-2 py-1 bg-stone-100 hover:bg-stone-200 rounded transition-colors"
    >
      {label} →
    </a>
  );
}
