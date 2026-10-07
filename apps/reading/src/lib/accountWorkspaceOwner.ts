import { useSyncExternalStore } from "react";

export interface WorkspaceOwnerSession {
  readonly subject: string | null;
  readonly epoch: number;
}

export interface WorkspaceOwnerAdmission {
  readonly session: WorkspaceOwnerSession;
  readonly state: "ready" | "suspended" | "retiring" | "failed";
}

let session: WorkspaceOwnerSession = { subject: null, epoch: 0 };
let revalidating: WorkspaceOwnerSession | null = null;
let transition: "ready" | "retiring" | "failed" = "ready";
const listeners = new Set<() => void>();
const retirementListeners = new Set<() => void>();
const confirmationListeners = new Set<() => void>();
const admissionListeners = new Set<(admission: WorkspaceOwnerAdmission) => void>();
let admission: WorkspaceOwnerAdmission = Object.freeze({ session, state: "ready" });
let notifying = false;
let confirming = false;

export function workspaceOwnerAdmission(): WorkspaceOwnerAdmission {
  return admission;
}

/** Synchronous local admission, not a credential or server-identity proof. */
export function subscribeWorkspaceOwnerAdmission(
  listener: (admission: WorkspaceOwnerAdmission) => void,
): () => void {
  admissionListeners.add(listener);
  return () => { admissionListeners.delete(listener); };
}

function refuseNotificationMutation(): void {
  if (notifying) throw new Error("Workspace owner cannot change during admission notification");
}

function notifyAdmission(failures: unknown[]): void {
  const state = transition === "ready" && revalidating === session ? "suspended" : transition;
  if (admission.session === session && admission.state === state) return;
  admission = Object.freeze({ session, state });
  notifying = true;
  try {
    for (const listener of [...admissionListeners]) {
      if (!admissionListeners.has(listener)) continue;
      try { listener(admission); }
      catch (error) { failures.push(error); }
    }
  } finally { notifying = false; }
}

function notifyConfirmation(failures: unknown[]): void {
  notifying = true;
  confirming = true;
  try {
    for (const listener of [...confirmationListeners]) {
      if (!confirmationListeners.has(listener)) continue;
      try { listener(); }
      catch (error) { failures.push(error); }
    }
  } finally {
    confirming = false;
    notifying = false;
  }
}

function finishAdmission(failures: unknown[]): void {
  if (failures.length > 0) {
    transition = "failed";
    notifyAdmission(failures);
  }
  notifyConfirmation(failures);
  if (failures.length > 0 && transition !== "failed") {
    transition = "failed";
    notifyAdmission(failures);
    notifyConfirmation(failures);
  }
  if (failures.length === 1) throw failures[0];
  if (failures.length > 1) throw new AggregateError(failures, "Workspace owner admission failed. Notification and cleanup outcomes are retained separately.");
}

export function workspaceOwnerSession(): WorkspaceOwnerSession {
  return session;
}

export function isWorkspaceOwnerSession(captured: WorkspaceOwnerSession): boolean {
  return transition === "ready" && captured === session && captured !== revalidating;
}

/** A cookie recheck suspends outbound work without destroying a same-owner draft. */
export function suspendWorkspaceOwner(): void {
  refuseNotificationMutation();
  if (transition !== "ready" || revalidating === session) return;
  revalidating = session;
  const failures: unknown[] = [];
  notifyAdmission(failures);
  if (failures.length > 0) finishAdmission(failures);
}

export function resumeWorkspaceOwner(captured = session): boolean {
  refuseNotificationMutation();
  if (captured !== session || transition !== "ready" || revalidating !== captured) return false;
  revalidating = null;
  const failures: unknown[] = [];
  notifyAdmission(failures);
  finishAdmission(failures);
  return true;
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
  if (!notifying && isWorkspaceOwnerSession(captured)) return Promise.resolve(true);
  return new Promise((resolve) => {
    const check = () => {
      // A later synchronous observer can still fail an earlier ready callback.
      if (!retired() && notifying && !confirming) return;
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
  refuseNotificationMutation();
  if (subject === session.subject && transition === "ready") return;
  if (transition === "retiring") throw new Error("Workspace owner replacement is already in progress");
  // Local cleanup still needs the outgoing subject, but no callback order or
  // resume may admit its token for outbound work after replacement begins.
  transition = "retiring";
  const failures: unknown[] = [];
  notifyAdmission(failures);
  try {
    for (const retire of retirementListeners) retire();
  } catch (error) {
    failures.push(error);
  }
  if (failures.length > 0) {
    finishAdmission(failures);
    return;
  }
  session = { subject, epoch: session.epoch + 1 };
  revalidating = null;
  transition = "ready";
  notifyAdmission(failures);
  notifying = true;
  try {
    for (const listener of [...listeners]) {
      if (!listeners.has(listener)) continue;
      try { listener(); }
      catch (error) { failures.push(error); }
    }
  } finally { notifying = false; }
  finishAdmission(failures);
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
