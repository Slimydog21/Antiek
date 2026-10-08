import { captureNotebookDraftOwner, finishNotebookDraftOwner, isCapturedNotebookDraftOwnerReady, isWorkspaceOwnerSession, notebookDraftKey, workspaceOwnerSession, type WorkspaceOwnerSession } from "./accountWorkspaceOwner";

export interface StoredNotebookDraft { html: string; etag: number }

export function readNotebookDraft(notebookId: string, owner = workspaceOwnerSession()): StoredNotebookDraft | null {
  const key = notebookDraftKey(notebookId, owner);
  if (typeof window === "undefined" || key === null || !isWorkspaceOwnerSession(owner)) return null;
  try {
    const html = window.localStorage.getItem(key);
    if (html === null) return null;
    return { html, etag: Number.parseInt(window.localStorage.getItem(key + ".etag") ?? "0", 10) || 0 };
  } catch { return null; }
}

export function writeNotebookDraft(notebookId: string, html: string, expectedEtag: number, owner: WorkspaceOwnerSession): number | null {
  const key = notebookDraftKey(notebookId, owner);
  if (typeof window === "undefined" || key === null || !isWorkspaceOwnerSession(owner)) return null;
  try {
    const current = Number.parseInt(window.localStorage.getItem(key + ".etag") ?? "0", 10) || 0;
    if (current !== expectedEtag) return null;
    const next = current + 1;
    window.localStorage.setItem(key, html);
    window.localStorage.setItem(key + ".etag", String(next));
    return next;
  } catch { return expectedEtag; }
}

export type NotebookDraftFinish =
  | { kind: "closed" | "refused" | "empty" | "unchanged" | "conflict" }
  | { kind: "written"; etag: number }
  | { kind: "failed"; error: unknown };

export interface CapturedNotebookDraft {
  record(html: string | null): boolean;
  finish(expectedEtag: number): NotebookDraftFinish;
}

/** Retain only edits recorded during this producer's ready lifetime, in its original notebook. */
export function captureNotebookDraft(notebookId: string, owner: WorkspaceOwnerSession): CapturedNotebookDraft | null {
  if (typeof window === "undefined") return null;
  const captured = captureNotebookDraftOwner(owner);
  if (captured === null) return null;
  let pending: string | null = null;
  let closed = false;
  return {
    record(html) {
      if (closed || !isCapturedNotebookDraftOwnerReady(captured)) return false;
      pending = html;
      return true;
    },
    finish(expectedEtag) {
      if (closed) return { kind: "closed" };
      closed = true;
      const html = pending;
      pending = null;
      const finalOwner = finishNotebookDraftOwner(captured);
      if (finalOwner === null) return { kind: "refused" };
      if (html === null) return { kind: "empty" };
      const key = notebookDraftKey(notebookId, finalOwner);
      if (key === null) return { kind: "refused" };
      try {
        const current = Number.parseInt(window.localStorage.getItem(key + ".etag") ?? "0", 10) || 0;
        if (current !== expectedEtag) return { kind: "conflict" };
        if (window.localStorage.getItem(key) === html) return { kind: "unchanged" };
        const next = current + 1;
        window.localStorage.setItem(key, html);
        window.localStorage.setItem(key + ".etag", String(next));
        return { kind: "written", etag: next };
      } catch (error) {
        return { kind: "failed", error };
      }
    },
  };
}
