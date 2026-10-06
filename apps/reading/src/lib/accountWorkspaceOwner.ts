import { useSyncExternalStore } from "react";

export interface WorkspaceOwnerSession {
  readonly subject: string | null;
  readonly epoch: number;
}

let session: WorkspaceOwnerSession = { subject: null, epoch: 0 };
let revalidating: WorkspaceOwnerSession | null = null;
const listeners = new Set<() => void>();
const retirementListeners = new Set<() => void>();

export function workspaceOwnerSession(): WorkspaceOwnerSession {
  return session;
}

export function isWorkspaceOwnerSession(captured: WorkspaceOwnerSession): boolean {
  return captured === session && captured !== revalidating;
}

/** A cookie recheck suspends outbound work without destroying a same-owner draft. */
export function suspendWorkspaceOwner(): void {
  revalidating = session;
}

export function resumeWorkspaceOwner(): void {
  revalidating = null;
}

export function subscribeWorkspaceOwner(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** Flush and retire old state before the trusted subject changes. */
export function beforeWorkspaceOwnerChange(listener: () => void): () => void {
  retirementListeners.add(listener);
  return () => { retirementListeners.delete(listener); };
}

/** A validated /auth/me answer establishes a subject; invalidation may only retire it to null. */
export function setWorkspaceOwner(subject: string | null): void {
  if (subject === session.subject) return;
  for (const retire of retirementListeners) retire();
  session = { subject, epoch: session.epoch + 1 };
  revalidating = null;
  for (const listener of listeners) listener();
}

export function useWorkspaceOwner(): WorkspaceOwnerSession {
  return useSyncExternalStore(subscribeWorkspaceOwner, workspaceOwnerSession, workspaceOwnerSession);
}

/** Legacy unowned bodies remain stored, but are never assigned to a login. */
export function accountStorageKey(key: string, captured = session): string | null {
  return captured.subject === null ? null : `${key}.owner.${encodeURIComponent(captured.subject)}`;
}

export function notebookDraftKey(notebookId: string, captured = session): string | null {
  return accountStorageKey(`antiek.notebook.${encodeURIComponent(notebookId)}`, captured);
}
