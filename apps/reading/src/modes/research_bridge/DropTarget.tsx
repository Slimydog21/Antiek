/**
 * DropTarget — receiver for ResearchBlock drags. Highlights yellow on
 * a valid block-drag enter. No animation (Lemon UI working aesthetic).
 */

import type { DragEvent, ReactNode } from "react";
import { useState } from "react";
import type { DragPayload } from "./types";
import { dragHasBlock, readBlockDrop } from "./drag";

export interface DropTargetProps {
  onDrop: (payload: DragPayload, event: DragEvent<HTMLDivElement>) => void;
  children: ReactNode;
  label?: ReactNode;
  enabled?: boolean;
  className?: string;
}

export function DropTarget({
  onDrop, children, label, enabled = true, className,
}: DropTargetProps) {
  const [highlighted, setHighlighted] = useState(false);

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    if (!enabled) return;
    if (!dragHasBlock(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    setHighlighted(true);
  };

  const handleDragLeave = (_e: DragEvent<HTMLDivElement>) => {
    setHighlighted(false);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    setHighlighted(false);
    if (!enabled) return;
    e.preventDefault();
    const payload = readBlockDrop(e);
    if (!payload) return;
    onDrop(payload, e);
  };

  const borderClasses = highlighted
    ? "border-sun-deep border-dashed border-2 bg-sun/10 dark:bg-sun/5"
    : "border-rule dark:border-charcoal-2 border-dashed border-2";

  return (
    <div
      className={["flex flex-col gap-2 p-3 rounded-md transition-none",
                  borderClasses, className ?? ""].filter(Boolean).join(" ")}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      data-research-bridge-drop-target=""
    >
      {label && (
        <div className="text-xs font-bold uppercase tracking-wide text-shadow-2 dark:text-moonlight">
          {label}
        </div>
      )}
      {children}
    </div>
  );
}
