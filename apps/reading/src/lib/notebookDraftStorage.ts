import { isWorkspaceOwnerSession, notebookDraftKey, workspaceOwnerSession, type WorkspaceOwnerSession } from "./accountWorkspaceOwner";

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
