/**
 * tabTitles.ts — the titles document tabs show, derived from their refs
 * (THREAD-CONTRACT §2.2 Needs: "title (derived from the ref)").
 *
 * The tab model stores no titles: a title belongs to the surface, and it can
 * change there. This module keeps a session cache keyed by (kind, ref), fed
 * two ways:
 *   - REGISTERED by a surface that already holds the title (the Write tree
 *     sync registers the piece and its section headings; a cross-pane open
 *     that knows the document's title passes it along);
 *   - RESOLVED on first sight from the corpus: a reader tab's book, a
 *     research tab's question, a draft's title (which also registers its
 *     sections).
 *
 * An entry is `loading`, `known` (the title, or null when the record exists
 * and has none) or `failed`. The label rules (tabLabels.ts) turn each state
 * into honest copy: a raw id is never a label.
 */
import { create } from "zustand";

import { getBook } from "../api/books";
import { getDeliverable, listInvestigations, type DeliverableDetailResponse } from "../lib/api";
import { sectionIdFromRef, sectionRefOf } from "./sectionRef";
import type { TabKind, TabNode } from "./tabTree";

export type TitleEntry =
  | { state: "loading" }
  | { state: "known"; title: string | null }
  | { state: "failed" };

export function titleKey(kind: TabKind, ref: string): string {
  return `${kind}\u0000${ref}`;
}

interface TabTitlesState {
  entries: Record<string, TitleEntry>;
}

export const useTabTitles = create<TabTitlesState>()(() => ({ entries: {} }));

function put(key: string, entry: TitleEntry): void {
  useTabTitles.setState((s) => ({ entries: { ...s.entries, [key]: entry } }));
}

/** Register a title a surface already holds (null = the record has none). */
export function setTabTitle(kind: TabKind, ref: string, title: string | null): void {
  put(titleKey(kind, ref), { state: "known", title: title?.trim() || null });
}

/** A Write piece's title and every section heading, in one pass. */
export function registerDeliverableTitles(detail: DeliverableDetailResponse): void {
  setTabTitle("document", `/write/${detail.deliverable_id}`, detail.title);
  for (const section of detail.sections) {
    setTabTitle("document", sectionRefOf(section.section_id), section.title);
  }
}

/** Resolve the title of `ref`; throw when it cannot be known. */
export type TitleResolver = (ref: string) => Promise<string | null>;

function investigationId(ref: string): string {
  return ref.startsWith("/inv/") ? ref.slice("/inv/".length) : ref;
}

let investigationList: Promise<Map<string, string | null>> | null = null;

async function questionOf(ref: string): Promise<string | null> {
  const id = investigationId(ref);
  investigationList ??= listInvestigations({ limit: 200 }).then(
    (r) => new Map(r.investigations.map((i) => [i.investigation_id, i.question])),
  );
  let list: Map<string, string | null>;
  try {
    list = await investigationList;
  } catch (e) {
    investigationList = null;
    throw e;
  }
  if (!list.has(id)) {
    // Newer than the cached list: the next request refetches.
    investigationList = null;
    throw new Error("investigation not listed");
  }
  return list.get(id) ?? null;
}

async function draftTitle(ref: string): Promise<string | null> {
  if (sectionIdFromRef(ref) !== null) {
    // A section's heading arrives with its piece (registered by the tree
    // sync or by the piece tab's own resolution), never by itself.
    throw new Error("section titles arrive with their piece");
  }
  if (!ref.startsWith("/write/")) throw new Error("not a draft ref");
  const detail = await getDeliverable(ref.slice("/write/".length));
  registerDeliverableTitles(detail);
  return detail.title;
}

const DEFAULT_RESOLVERS: Partial<Record<TabKind, TitleResolver>> = {
  reader: async (ref) => (await getBook(ref)).title,
  research: questionOf,
  thread: questionOf,
  document: draftTitle,
};

let resolvers: Partial<Record<TabKind, TitleResolver>> = DEFAULT_RESOLVERS;

/** Test/story seam: replace the resolvers (null restores the defaults). */
export function setTitleResolvers(next: Partial<Record<TabKind, TitleResolver>> | null): void {
  resolvers = next ?? DEFAULT_RESOLVERS;
}

/** Ask for a tab's title once; later calls for the same ref are no-ops. */
export function requestTabTitle(tab: Pick<TabNode, "kind" | "ref">): void {
  const key = titleKey(tab.kind, tab.ref);
  if (useTabTitles.getState().entries[key]) return;
  const resolve = resolvers[tab.kind];
  if (!resolve) return;
  put(key, { state: "loading" });
  resolve(tab.ref).then(
    (title) => {
      // A registration that landed meanwhile is at least as fresh.
      if (useTabTitles.getState().entries[key]?.state === "loading") {
        put(key, { state: "known", title: title?.trim() || null });
      }
    },
    () => {
      if (useTabTitles.getState().entries[key]?.state === "loading") put(key, { state: "failed" });
    },
  );
}

/** Test seam. */
export function resetTabTitles(): void {
  investigationList = null;
  resolvers = DEFAULT_RESOLVERS;
  useTabTitles.setState({ entries: {} });
}
