/**
 * composerChips.ts — @agent and #source chips (SPR-07 M2; refs pattern
 * 11). The draft serializes deterministically as `@A #S body` so a reload
 * and a transcript read the same; Backspace on an empty body removes the
 * last chip. Sources are the selected project's members when the SPR-06
 * tree is ready, else the open left reader tabs (an honest pre-tree
 * fallback, never an invented member list).
 */
import type { Selection } from "../contracts/selection";
import { findProjectPath, type ContextTree } from "../contracts/tree";

export interface ComposerChip {
  kind: "agent" | "source";
  id: string;
  label: string;
}

export interface ChipCandidate {
  id: string;
  label: string;
}

export function serializeDraft(chips: readonly ComposerChip[], body: string): string {
  const prefix = chips.map((c) => `${c.kind === "agent" ? "@" : "#"}${c.label}`).join(" ");
  if (!prefix) return body;
  return body ? `${prefix} ${body}` : prefix;
}

export function backspaceRemovesLastChip(chips: readonly ComposerChip[], body: string): { chips: ComposerChip[]; removed: ComposerChip | null } {
  if (body !== "" || chips.length === 0) return { chips: [...chips], removed: null };
  return { chips: chips.slice(0, -1), removed: chips[chips.length - 1] };
}

export function sourceCandidates(
  tree: ContextTree,
  selection: Pick<Selection, "projectId" | "subProjectId">,
  leftTabs: readonly { id: string; title: string }[],
): ChipCandidate[] {
  if (tree.status === "ready") {
    const path = findProjectPath(tree, selection.subProjectId ?? selection.projectId);
    const node = path?.at(-1) ?? null;
    // Absent members = not fetched, NOT "no members" (tree.ts): fall back.
    if (node?.members) return node.members.map((m) => ({ id: m.member_id, label: m.member_id }));
  }
  return leftTabs.map((t) => ({ id: t.id, label: t.title }));
}
