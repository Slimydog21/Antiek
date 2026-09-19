/**
 * Chase collective selection — pure rules for multi-select deep-research
 * instances that draft-merge as one unit.
 *
 * Operator vision: pick multiple sub-agent chases (completed) and prompt /
 * merge them as a cohesive unit. Selection is explicit but defaults to all
 * *ready* (completed) chase ids so a single "draft ready" still works when
 * the reader has not touched checkboxes.
 *
 * Pure + hard-to-vary: no DOM, no clocks, no I/O. Unit tests pin the contract.
 */

/** Stable, de-duplicated selection after a toggle. */
export function toggleChaseSelection(
  selected: readonly string[],
  id: string,
): string[] {
  const set = new Set(selected);
  if (set.has(id)) set.delete(id);
  else set.add(id);
  return Array.from(set);
}

/**
 * Intersection of the reader's selection with currently-ready (completed)
 * chase ids, preserving the order of `readyIds` so compose payloads stay
 * deterministic for a given ready list.
 */
export function selectedReadyIds(
  selected: readonly string[],
  readyIds: readonly string[],
): string[] {
  if (readyIds.length === 0) return [];
  const selectedSet = new Set(selected);
  // Empty selection ⇒ default-all-ready (no checkbox interaction yet).
  if (selectedSet.size === 0) return [...readyIds];
  return readyIds.filter((id) => selectedSet.has(id));
}

/** Draft merge requires at least two completed members in the collective. */
export function canDraftCollective(memberIds: readonly string[]): boolean {
  return memberIds.length >= 2;
}

/**
 * Label for the draft affordance — honest about whether selection trimmed
 * the ready set.
 */
export function collectiveDraftTitle(
  selectedReady: readonly string[],
  readyCount: number,
): string {
  if (selectedReady.length < 2) {
    return "Select at least two completed chases to draft-merge as one unit";
  }
  if (selectedReady.length < readyCount) {
    return `Draft a no-mutation merge of ${selectedReady.length} selected completed chases`;
  }
  return "Draft a no-mutation merge of completed chase artifacts";
}
