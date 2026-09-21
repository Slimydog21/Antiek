import { useCallback, useState } from "react";

import type { PaletteDragPayload } from "../CreationStudio/BlockPalette";
import { parsePaletteDrag } from "./insightLegoSlot";

interface ThoughtPartnerFocusTrayProps {
  slotted: PaletteDragPayload[];
  onSlot: (payload: PaletteDragPayload) => void;
  onRemove: (blockId: string) => void;
}

/** Drop target and removable chips for the thought-partner's focused insights. */
export default function ThoughtPartnerFocusTray({
  slotted,
  onSlot,
  onRemove,
}: ThoughtPartnerFocusTrayProps) {
  const [dropActive, setDropActive] = useState(false);

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setDropActive(true);
  }, []);

  const onDragLeave = useCallback((event: React.DragEvent) => {
    if (event.currentTarget.contains(event.relatedTarget as Node)) return;
    setDropActive(false);
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      setDropActive(false);
      const payload = parsePaletteDrag(event.dataTransfer);
      if (payload) onSlot(payload);
    },
    [onSlot],
  );

  return (
    <div
      data-testid="thought-partner-focus-tray"
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={
        "min-h-[3.5rem] border border-dashed rounded p-2 space-y-1.5 transition-colors " +
        (dropActive
          ? "border-ocean bg-ocean/10"
          : "border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-3")
      }
    >
      <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        Focus tray
        {slotted.length ? ` · ${slotted.length}` : ""}
      </p>
      {slotted.length === 0 ? (
        <p className="text-[11px] text-ink-mute dark:text-moonlight italic">
          Drop insight Legos here (or tap + on the shelf).
        </p>
      ) : (
        <ul className="flex flex-wrap gap-1" aria-label="Slotted insights">
          {slotted.map((slot) => (
            <li
              key={slot.block_id}
              className="inline-flex items-center gap-1 max-w-full px-1.5 py-0.5 rounded border border-ocean/40 bg-ocean/10 text-[10px] font-serif text-ink dark:text-bright"
              data-testid="slotted-insight-chip"
            >
              <span className="truncate" title={slot.label}>
                {slot.label}
              </span>
              <button
                type="button"
                aria-label={`Remove ${slot.label}`}
                className="font-mono text-ink-mute hover:text-emperor"
                onClick={() => onRemove(slot.block_id)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
