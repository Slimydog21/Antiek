import { useSyncExternalStore } from "react";

export interface WorkspaceOwnerSession {
  readonly subject: string | null;
  readonly epoch: number;
}

let session: WorkspaceOwnerSession = { subject: null, epoch: 0 };
let revalidating: WorkspaceOwnerSession | null = null;
let transition: "ready" | "retiring" | "failed" = "ready";
const listeners = new Set<() => void>();
const retirementListeners = new Set<() => void>();
const confirmationListeners = new Set<() => void>();

export function workspaceOwnerSession(): WorkspaceOwnerSession {
  return session;
}

export function isWorkspaceOwnerSession(captured: WorkspaceOwnerSession): boolean {
  return transition === "ready" && captured === session && captured !== revalidating;
}

/** A cookie recheck suspends outbound work without destroying a same-owner draft. */
export function suspendWorkspaceOwner(): void {
  revalidating = session;
}

export function resumeWorkspaceOwner(): void {
  revalidating = null;
  for (const listener of confirmationListeners) listener();
}

/** Hold a completion through a cookie recheck; replacement or disposal refuses it.
 * Callers must still check their resource/lifetime after awaiting confirmation. */
export function awaitWorkspaceOwnerSession(
  captured: WorkspaceOwnerSession,
  signal?: AbortSignal,
): Promise<boolean> {
  const retired = () => transition !== "ready" || captured.subject === null
    || captured !== session || signal?.aborted === true;
  if (retired()) return Promise.resolve(false);
  if (isWorkspaceOwnerSession(captured)) return Promise.resolve(true);
  return new Promise((resolve) => {
    const check = () => {
      if (!retired() && !isWorkspaceOwnerSession(captured)) return;
      confirmationListeners.delete(check);
      signal?.removeEventListener("abort", check);
      resolve(!retired() && isWorkspaceOwnerSession(captured));
    };
    confirmationListeners.add(check);
    signal?.addEventListener("abort", check, { once: true });
    check();
  });
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
  if (subject === session.subject && transition === "ready") return;
  if (transition === "retiring") throw new Error("Workspace owner replacement is already in progress");
  // Local cleanup still needs the outgoing subject, but no callback order or
  // resume may admit its token for outbound work after replacement begins.
  transition = "retiring";
  try {
    for (const retire of retirementListeners) retire();
  } catch (error) {
    transition = "failed";
    for (const listener of confirmationListeners) listener();
    throw error;
  }
  session = { subject, epoch: session.epoch + 1 };
  revalidating = null;
  transition = "ready";
  for (const listener of confirmationListeners) listener();
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
