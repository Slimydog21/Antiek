import { useEffect, useState } from "react";

import {
  searchBlocks,
  type BlockKind,
  type BlockSearchHit,
} from "../../lib/api";

/**
 * Block palette — the operator's search-and-drag surface.
 *
 * Sprint 14: native HTML5 drag-drop. The dragged payload is a JSON
 * envelope ``{from: "palette", block_kind, block_id, label}`` so
 * SectionCard's drop handler can distinguish "new attach" from
 * "section→section reorder" (whose payload is
 * ``{from: "section", section_id, block_kind, block_id, block_index}``).
 *
 * Sprint 15 may swap this for @dnd-kit if multi-touch / mobile
 * support becomes a priority. The HTML5 API is sufficient for the
 * desktop-first MVP.
 */
export interface PaletteDragPayload {
  from: "palette";
  block_kind: BlockKind;
  block_id: string;
  label: string;
}

export const DRAG_MIME = "application/x-antiek-block";

export default function BlockPalette() {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<BlockSearchHit[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const handle = setTimeout(() => {
      void (async () => {
        setLoading(true);
        try {
          const r = await searchBlocks(q, 30);
          setHits(r.hits);
        } catch {
          setHits([]);
        } finally {
          setLoading(false);
        }
      })();
    }, 250);
    return () => clearTimeout(handle);
  }, [q]);

  return (
    <div className="bg-ice-0 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 rounded-md p-3 flex flex-col gap-2 min-h-0">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-ink dark:text-bright uppercase tracking-wide">
          Block palette
        </h3>
        {loading && (
          <span className="text-xs text-ink-mute dark:text-moonlight">searching…</span>
        )}
      </div>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search insights, claims, notes…"
        className="w-full px-2 py-1.5 text-xs border border-rule dark:border-charcoal-1 rounded focus:outline-none focus:ring-2 focus:ring-sun"
      />
      <ul className="flex-1 overflow-y-auto space-y-1 min-h-0">
        {hits.length === 0 && !loading && (
          <li className="text-xs text-ink-mute dark:text-moonlight italic px-1 py-2">
            No matches. Try a broader query, or run an investigation
            to produce more blocks.
          </li>
        )}
        {hits.map((h) => (
          <li key={`${h.block_kind}:${h.block_id}`}>
            <div
              draggable
              onDragStart={(e) => {
                const payload: PaletteDragPayload = {
                  from: "palette",
                  block_kind: h.block_kind,
                  block_id: h.block_id,
                  label: h.label,
                };
                e.dataTransfer.setData(DRAG_MIME, JSON.stringify(payload));
                e.dataTransfer.effectAllowed = "copy";
              }}
              className="px-2 py-1.5 border border-rule dark:border-charcoal-1 hover:border-glacial-1 dark:border-slate-1 hover:bg-ice-1 dark:bg-charcoal-2 rounded cursor-grab active:cursor-grabbing"
              title={h.body}
            >
              <p className="text-xs font-medium text-ink dark:text-bright truncate">
                {h.label}
              </p>
              <p className="text-[10px] text-shadow-1 dark:text-moonlight truncate">
                {h.block_kind}
                {h.source_tier ? ` · Tier ${h.source_tier}` : ""}
                {h.document_title ? ` · ${h.document_title}` : ""}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
