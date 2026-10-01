/**
 * tabLabels.ts — what a document tab is called, from its title entry and
 * its branch origin. Pure, so the strip, the tree panel, the path header,
 * the toasts and the stories share one rule.
 *
 * Order:
 *   1. a branch INSIDE its parent's surface (a footnote hop on the same
 *      document) is named by its passage: the title would only repeat the
 *      parent's;
 *   2. otherwise the surface's title, when known;
 *   3. otherwise the branch passage, when there is one;
 *   4. otherwise a plain noun for the kind ("Document", "Research",
 *      "Section"…), or "Untitled …" when the record is known to have no
 *      title. The hierarchical number beside every label keeps two nouns
 *      apart.
 * A raw ref (a document id, "/inv/<id>", "section:<uuid>") is never a label.
 */
import { sectionIdFromRef } from "./sectionRef";
import type { TitleEntry } from "./tabTitles";
import type { BranchKind, TabKind, TabNode } from "./tabTree";

export interface TabLabel {
  text: string;
  /** Where the text came from; `fallback` renders a touch quieter. */
  source: "title" | "passage" | "fallback";
  /** The title is still being looked up. */
  pending: boolean;
}

const NOUN: Record<TabKind, string> = {
  reader: "Document",
  research: "Research",
  document: "Draft",
  // Right-side (agent) kinds: the client spawns none yet (A14), but a tree
  // read from the server holds them.
  dialogue: "Dialogue",
  reformat: "Reformat",
  diligence: "Diligence",
  island: "Island",
  findings: "Findings",
  flags: "Flags",
  block: "Block",
};

const BRANCH_NOUN: Record<BranchKind, string> = {
  footnote: "Footnote",
  reference: "Reference",
  citation: "Citation",
  island: "Island",
  research: "Research",
  manual: "Branch",
  agent: "From an agent",
  derivation: "Reformatted",
};

/** The one-word name of a tab's kind (sections read as "Section"). */
export function kindNoun(tab: Pick<TabNode, "kind" | "ref">): string {
  return tab.kind === "document" && sectionIdFromRef(tab.ref) !== null ? "Section" : NOUN[tab.kind];
}

export function labelForTab(
  tab: Pick<TabNode, "kind" | "ref" | "branch_origin">,
  parent: Pick<TabNode, "kind" | "ref"> | null | undefined,
  entry: TitleEntry | undefined,
): TabLabel {
  const pending = entry?.state === "loading";
  const passage = tab.branch_origin?.anchor?.quote?.replace(/\s+/g, " ").trim() || null;
  const title = entry?.state === "known" ? entry.title?.trim() || null : null;
  const sameSurface = !!parent && parent.kind === tab.kind && parent.ref === tab.ref;

  if (passage && sameSurface) return { text: passage, source: "passage", pending };
  if (title) return { text: title, source: "title", pending };
  if (passage) return { text: passage, source: "passage", pending };
  if (sameSurface && tab.branch_origin) {
    return { text: BRANCH_NOUN[tab.branch_origin.kind], source: "fallback", pending };
  }
  const noun = kindNoun(tab);
  const untitled = entry?.state === "known" && title === null;
  return { text: untitled ? `Untitled ${noun.toLowerCase()}` : noun, source: "fallback", pending };
}
