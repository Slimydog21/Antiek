/**
 * forkLineage.ts — the session's view of document forks (thread-merge +
 * document fork SPR-01, verdict C's chrome).
 *
 * The tab model (tabTree.ts) is NAVIGATION state and stores no fork truth;
 * the fork truth lives server-side in document_forks. This store is the
 * client-side index of what this session has LEARNED from the fork routes,
 * so the strip's badge ("this tab is a fork of …") and the source tab's
 * forks chip ("n fork ▸") can render from the chrome without re-fetching
 * per paint:
 *
 *   fed two ways —
 *     - the reader mount asks fetchDocumentForks(documentId) once per open
 *       (one GET per document, like the reading-state bus's);
 *     - the companion's fork action records the row its POST returned;
 *   read two ways —
 *     - byFork: document id → the row where it IS the fork (badge);
 *     - byParent: document id → rows whose parent it is (the chip).
 *
 * Session-scoped like tabTitles: a reload re-learns from the server. A
 * failed fetch records NOTHING — an absent badge is honest, a wrong one is
 * not.
 */
import { create } from "zustand";

import { listForks, type DocumentFork } from "../api/forks";
import { awaitWorkspaceOwnerSession, beforeWorkspaceOwnerChange, isWorkspaceOwnerSession, workspaceOwnerSession, type WorkspaceOwnerSession } from "../lib/accountWorkspaceOwner";

interface ForkLineageState {
  /** document id → the fork row where it is the CHILD. */
  byFork: Record<string, DocumentFork>;
  /** document id → the fork rows whose PARENT it is (creation order). */
  byParent: Record<string, DocumentFork[]>;
}

export const useForkLineage = create<ForkLineageState>()(() => ({
  byFork: {},
  byParent: {},
}));

function put(state: ForkLineageState, row: DocumentFork): ForkLineageState {
  const siblings = state.byParent[row.parent_document_id] ?? [];
  const nextSiblings = siblings.some((s) => s.fork_id === row.fork_id)
    ? siblings.map((s) => (s.fork_id === row.fork_id ? row : s))
    : [...siblings, row];
  return {
    byFork: { ...state.byFork, [row.fork_document_id]: row },
    byParent: { ...state.byParent, [row.parent_document_id]: nextSiblings },
  };
}

/** Record a fork row the session holds (a creation response, a list read). */
export function recordFork(row: DocumentFork, owner: WorkspaceOwnerSession = workspaceOwnerSession()): void {
  if (owner.subject === null || !isWorkspaceOwnerSession(owner)) return;
  useForkLineage.setState((s) => put(s, row));
}

/** The lineage the session knows for a document, both directions. */
export function forkLineageOf(documentId: string): {
  forkedFrom: DocumentFork | null;
  forks: DocumentFork[];
} {
  const owner = workspaceOwnerSession();
  if (owner.subject === null || !isWorkspaceOwnerSession(owner)) return { forkedFrom: null, forks: [] };
  const s = useForkLineage.getState();
  return {
    forkedFrom: s.byFork[documentId] ?? null,
    forks: s.byParent[documentId] ?? [],
  };
}

/** One in-flight fetch per document (the reader mount and a chip render can
 *  ask on the same tick). */
const inflight = new Map<string, Promise<void>>();

/** Learn a document's fork neighbourhood from the server (both directions,
 *  one GET). Never rejects: a failure leaves the store untouched. */
export function fetchDocumentForks(documentId: string): Promise<void> {
  const owner = workspaceOwnerSession();
  if (owner.subject === null || !isWorkspaceOwnerSession(owner)) return Promise.resolve();
  const running = inflight.get(documentId);
  if (running) return running;
  const run = listForks(documentId)
    .then(async (resp) => {
      while (!isWorkspaceOwnerSession(owner)) {
        if (!await awaitWorkspaceOwnerSession(owner)) return;
      }
      if (resp.forked_from) recordFork(resp.forked_from, owner);
      for (const row of resp.forks) recordFork(row, owner);
    })
    .catch(() => undefined)
    .finally(() => {
      if (inflight.get(documentId) === run) inflight.delete(documentId);
    });
  inflight.set(documentId, run);
  return run;
}

/** Test seam. */
export function resetForkLineage(): void {
  inflight.clear();
  useForkLineage.setState({ byFork: {}, byParent: {} });
}

beforeWorkspaceOwnerChange(resetForkLineage);
