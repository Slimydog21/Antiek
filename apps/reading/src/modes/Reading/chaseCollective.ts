import type { InvestigationSummary } from "../../lib/api";

export interface CompletedReadingChase {
  investigationId: string;
  question: string;
}

/** Completed children of this book's reading thread, in substrate document order. */
export function completedReadingChases(
  investigations: InvestigationSummary[],
  readingThreadId: string,
): CompletedReadingChase[] {
  return investigations
    .filter(
      (item) =>
        item.parent_investigation_id === readingThreadId &&
        item.status === "completed",
    )
    .map((item) => ({
      investigationId: item.investigation_id,
      question: item.question?.trim() || "Untitled chase",
    }));
}

/**
 * Reconcile selection when polling changes the available chases.
 *
 * Untouched selection follows the convenient default of every completed
 * chase. Once touched, it only loses unavailable ids; an intentional empty
 * selection therefore remains empty.
 */
export function reconcileChaseSelection(
  availableIds: string[],
  selectedIds: string[],
  touched: boolean,
): string[] {
  if (!touched) return [...availableIds];
  const selected = new Set(selectedIds);
  return availableIds.filter((id) => selected.has(id));
}

/** Toggle one chase while retaining the stable order presented by the book. */
export function toggleChaseSelection(
  availableIds: string[],
  selectedIds: string[],
  investigationId: string,
): string[] {
  const selected = new Set(selectedIds);
  if (selected.has(investigationId)) selected.delete(investigationId);
  else selected.add(investigationId);
  return availableIds.filter((id) => selected.has(id));
}
