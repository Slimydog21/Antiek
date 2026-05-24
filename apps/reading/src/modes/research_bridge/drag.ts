/**
 * Native HTML5 drag/drop primitive for the research bridge.
 *
 * No 3rd-party drag library. Bespoke MIME type isolates from
 * foreign drags. Desktop-only.
 */

import type { DragEvent } from "react";
import type { DragPayload, ResearchSource } from "./types";

export const DRAG_MIME = "application/vnd.antiek-research-block";
export const DRAG_TEXT_MIME = "text/plain";


export function beginBlockDrag(
  event: DragEvent<HTMLElement>,
  block: { document_id: string; source: ResearchSource },
): void {
  const payload: DragPayload = {
    block_id: block.document_id,
    source: block.source,
  };
  const json = JSON.stringify(payload);
  event.dataTransfer.setData(DRAG_MIME, json);
  event.dataTransfer.setData(DRAG_TEXT_MIME, json);
  event.dataTransfer.effectAllowed = "copyMove";
}


export function readBlockDrop(event: DragEvent<HTMLElement>): DragPayload | null {
  const raw = event.dataTransfer.getData(DRAG_MIME)
            || event.dataTransfer.getData(DRAG_TEXT_MIME);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as DragPayload;
    if (!parsed || typeof parsed.block_id !== "string") return null;
    if (typeof parsed.source !== "string") return null;
    return parsed;
  } catch {
    return null;
  }
}


export function dragHasBlock(event: DragEvent<HTMLElement>): boolean {
  const types = event.dataTransfer.types;
  for (let i = 0; i < types.length; i++) {
    const t = types[i];
    if (t === DRAG_MIME || t === DRAG_TEXT_MIME) return true;
  }
  return false;
}
