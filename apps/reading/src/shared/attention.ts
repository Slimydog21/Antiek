/**
 * attention.ts — attention-priority rollup (herdr transfer, P0-2).
 *
 * herdr's strategy (src/detect, sidebar rollup): a workspace's attention is
 * the max over its panes, so one blocked agent reddens every ancestor row —
 * session group, tree node, palette entry, nav rail. Antiek's equivalent:
 * a research session (parent + spawned children) rolls up to one dot, and
 * the whole research surface rolls up to one badge.
 *
 * Pure module: no React, no storage. Priority ladder (herdr-informed):
 *   blocked        (4) — a failed research needs the operator's eyes
 *   unseen-done    (3) — completed and never opened (the unread flag)
 *   working        (2) — actively running
 *   done/stopped   (1) — finished, seen
 *   unavailable    (0) — a dangling id, no row
 */
import type { ResearchState } from "./researchState";

export interface AttentionInput {
  state: ResearchState;
  /** Unseen-done outranks working (an unread completion is a to-do). */
  unseen?: boolean;
}

/** Raw state priority — `unseen` boosts `done` above `working`. */
export function attentionScore(input: AttentionInput): number {
  switch (input.state) {
    case "blocked":
      return 4;
    case "done":
      return input.unseen ? 3 : 1;
    case "working":
      return 2;
    case "stopped":
      return 1;
    case "unavailable":
      return 0;
  }
}

/** The state that most needs the operator, or null when nothing does.
 *  Empty input rolls up to null (no attention), never a phantom state. */
export function aggregateAttention(
  items: readonly AttentionInput[],
): ResearchState | null {
  if (items.length === 0) return null;
  let best: ResearchState | null = null;
  let bestScore = -1;
  for (const item of items) {
    const score = attentionScore(item);
    if (score > bestScore) {
      bestScore = score;
      best = item.state;
    }
  }
  return best;
}

/** Whether a rollup result should render as "needs you" (the rail badge
 *  lights up only for blocked or unseen-done — working is normal, not a
 *  summons). */
export function isSummoning(state: ResearchState | null): boolean {
  return state === "blocked";
}

/** Whether a rollup result includes unseen completions (drives the unread
 *  count badge). */
export function hasUnseen(items: readonly AttentionInput[]): boolean {
  return items.some((i) => i.state === "done" && i.unseen === true);
}
