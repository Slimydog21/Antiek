/**
 * agentDraft.ts — the composer's draft (SPR-07 M1; refs pattern 22).
 *
 * sessionStorage under agentDraftKey() (account-scoped; null ⇒ no I/O).
 * Every access is wrapped: a private window, a quota, a blocked store all
 * read as "". Writes happen only while the owner session that mounted the
 * hook still holds (isWorkspaceOwnerSession). Module load registers a
 * beforeWorkspaceOwnerChange purge of every `antiek.agent.` key: belt and
 * braces beside the account-scoped key (graft d).
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { beforeWorkspaceOwnerChange, isWorkspaceOwnerSession, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";

export const AGENT_STORAGE_PREFIX = "antiek.agent.";
export const DRAFT_DEBOUNCE_MS = 150;

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

export function readAgentDraft(key: string | null): string {
  if (key === null) return "";
  try {
    return storage()?.getItem(key) ?? "";
  } catch {
    return "";
  }
}

export function writeAgentDraft(key: string | null, value: string, owner = workspaceOwnerSession()): void {
  if (key === null || !isWorkspaceOwnerSession(owner)) return;
  try {
    const s = storage();
    if (!s) return;
    if (value) s.setItem(key, value);
    else s.removeItem(key);
  } catch {
    // quota / blocked storage: the in-memory draft stands
  }
}

export function clearAgentDraft(key: string | null): void {
  if (key === null) return;
  try {
    storage()?.removeItem(key);
  } catch {
    // ignore
  }
}

/** Every sessionStorage key under the agent prefix, gone. */
export function purgeAgentDrafts(): void {
  try {
    const s = storage();
    if (!s) return;
    const doomed: string[] = [];
    for (let i = 0; i < s.length; i++) {
      const k = s.key(i);
      if (k && k.startsWith(AGENT_STORAGE_PREFIX)) doomed.push(k);
    }
    for (const k of doomed) s.removeItem(k);
  } catch {
    // ignore
  }
}

beforeWorkspaceOwnerChange(purgeAgentDrafts);

/** Reads on mount; writes 150 ms after the last change, only while the
 *  mounting owner session holds. */
export function useAgentDraft(key: string | null): [string, (value: string) => void] {
  const owner = useRef(workspaceOwnerSession());
  const [draft, setDraftState] = useState(() => readAgentDraft(key));
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    owner.current = workspaceOwnerSession();
    setDraftState(readAgentDraft(key));
  }, [key]);

  useEffect(() => () => { if (timer.current !== null) clearTimeout(timer.current); }, []);

  const setDraft = useCallback((value: string) => {
    setDraftState(value);
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      timer.current = null;
      writeAgentDraft(key, value, owner.current);
    }, DRAFT_DEBOUNCE_MS);
  }, [key]);

  return [draft, setDraft];
}
