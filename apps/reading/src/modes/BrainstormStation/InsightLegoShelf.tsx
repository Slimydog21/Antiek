/**
 * Surface E insight Lego shelf — supply side for TP slotting (§4.5).
 *
 * Same `GET /blocks/search` + `PaletteDragPayload` / `DRAG_MIME` as
 * CreationStudio BlockPalette and Write Repository. Click-to-slot
 * mirrors drag for keyboard / small-screen operators.
 */
import { useEffect, useState } from "react";

import { searchBlocks, type BlockSearchHit } from "../../lib/api";
import type { PaletteDragPayload } from "../CreationStudio/BlockPalette";
import { DRAG_MIME } from "../CreationStudio/BlockPalette";

export interface InsightLegoShelfProps {
  /** Optional: click adds without requiring drag (a11y / touch). */
  onSlot?: (payload: PaletteDragPayload) => void;
  className?: string;
}

function toPayload(hit: BlockSearchHit): PaletteDragPayload {
  return {
    from: "palette",
    block_kind: hit.block_kind,
    block_id: hit.block_id,
    label: hit.label,
  };
}

export default function InsightLegoShelf({
  onSlot,
  className,
}: InsightLegoShelfProps) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<BlockSearchHit[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const handle = setTimeout(() => {
      void (async () => {
        setLoading(true);
        try {
          const r = await searchBlocks(q, 24);
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
    <div
      className={
        "border border-rule dark:border-charcoal-1 rounded p-2 space-y-2 bg-ice-0 dark:bg-charcoal-3 " +
        (className ?? "")
      }
      data-testid="insight-lego-shelf"
    >
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-[10px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Insight Legos
        </h4>
        {loading ? (
          <span className="text-[10px] text-ink-mute dark:text-moonlight">
            searching…
          </span>
        ) : null}
      </div>
      <input
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search graph insights…"
        aria-label="Search insight Legos"
        className="w-full px-2 py-1 text-[11px] border border-rule dark:border-charcoal-1 rounded bg-ice-1 dark:bg-charcoal-2 focus:outline-none focus:ring-1 focus:ring-sun"
      />
      <ul className="max-h-36 overflow-y-auto space-y-1" aria-label="Draggable insights">
        {hits.length === 0 && !loading ? (
          <li className="text-[11px] text-ink-mute dark:text-moonlight italic px-1 py-2">
            No matches. Research deposits insights here as Lego blocks.
          </li>
        ) : null}
        {hits.map((h) => {
          const payload = toPayload(h);
          return (
            <li key={`${h.block_kind}:${h.block_id}`}>
              <div
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData(DRAG_MIME, JSON.stringify(payload));
                  e.dataTransfer.effectAllowed = "copy";
                }}
                className="flex items-start gap-1 px-1.5 py-1 border border-rule dark:border-charcoal-1 rounded cursor-grab hover:border-ocean bg-ice-1 dark:bg-charcoal-2"
                title="Drag into the thought-partner focus tray"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] font-serif text-ink dark:text-bright truncate">
                    {h.label}
                  </p>
                  <p className="text-[9px] font-mono text-ink-mute dark:text-moonlight truncate">
                    {h.block_kind}
                    {h.document_title ? ` · ${h.document_title}` : ""}
                  </p>
                </div>
                {onSlot ? (
                  <button
                    type="button"
                    className="shrink-0 text-[10px] font-mono text-ocean hover:underline px-1"
                    aria-label={`Slot ${h.label}`}
                    onClick={() => onSlot(payload)}
                  >
                    +
                  </button>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
