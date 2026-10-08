/**
 * agentDraft.ts — the composer's draft (SPR-07 M1; refs pattern 22).
 *
 * sessionStorage under agentDraftKey() (account-scoped; null ⇒ no I/O).
 * Every access is wrapped: a private window, a quota, a blocked store all
 * read as "". A write carries the owner session captured when the words
 * were typed (setDraft), and lands only while that session still holds
 * (isWorkspaceOwnerSession); a pending write is flushed, under that same
 * check, when the key changes or the hook unmounts (a quick tab switch
 * loses no words; a retired owner's words are refused, never resurrected:
 * repair 2026-10-07T22:40Z, finding 3). Purge (belt and braces beside the
 * account-scoped key, graft d): every `antiek.agent.` key goes before a
 * NON-null subject is replaced; after any admission, every key owned by
 * another subject goes. A page load's null → subject admission therefore
 * keeps that subject's drafts (M1 "survives a reload" no longer depends on
 * module load order; finding 4).
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { beforeWorkspaceOwnerChange, isWorkspaceOwnerSession, subscribeWorkspaceOwner, workspaceOwnerSession, type WorkspaceOwnerSession } from "../../lib/accountWorkspaceOwner";

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

function agentDraftKeys(s: Storage): string[] {
  const out: string[] = [];
  for (let i = 0; i < s.length; i++) {
    const k = s.key(i);
    if (k && k.startsWith(AGENT_STORAGE_PREFIX)) out.push(k);
  }
  return out;
}

/** Every sessionStorage key under the agent prefix, gone. */
export function purgeAgentDrafts(): void {
  try {
    const s = storage();
    if (!s) return;
    for (const k of agentDraftKeys(s)) s.removeItem(k);
  } catch {
    // ignore
  }
}

/** Every agent key not owned by `subject` (accountStorageKey's
 *  `.owner.<subject>` suffix), gone; null ⇒ every key. */
export function purgeForeignAgentDrafts(subject: string | null): void {
  try {
    const s = storage();
    if (!s) return;
    const own = subject === null ? null : `.owner.${encodeURIComponent(subject)}`;
    for (const k of agentDraftKeys(s)) if (own === null || !k.endsWith(own)) s.removeItem(k);
  } catch {
    // ignore
  }
}

// A signed-in subject's retirement purges everything; a page load's
// null → subject admission is not a retirement, so it keeps the admitted
// subject's drafts and drops any other subject's (finding 4).
beforeWorkspaceOwnerChange(() => { if (workspaceOwnerSession().subject !== null) purgeAgentDrafts(); });
subscribeWorkspaceOwner(() => purgeForeignAgentDrafts(workspaceOwnerSession().subject));

interface PendingWrite {
  key: string | null;
  value: string;
  /** The session that typed the words; the write lands only while it holds. */
  owner: WorkspaceOwnerSession;
  timer: ReturnType<typeof setTimeout>;
}

/** Reads on mount; writes 150 ms after the last change, only while the
 *  owner session that typed the words still holds; a pending write is
 *  flushed under that same check when the key changes or on unmount. */
export function useAgentDraft(key: string | null): [string, (value: string) => void] {
  const [draft, setDraftState] = useState(() => readAgentDraft(key));
  const pending = useRef<PendingWrite | null>(null);

  const flush = useCallback(() => {
    const w = pending.current;
    if (w === null) return;
    pending.current = null;
    clearTimeout(w.timer);
    writeAgentDraft(w.key, w.value, w.owner);
  }, []);

  useEffect(() => {
    setDraftState(readAgentDraft(key));
    return flush;
  }, [key, flush]);

  const setDraft = useCallback((value: string) => {
    setDraftState(value);
    if (pending.current !== null) clearTimeout(pending.current.timer);
    pending.current = {
      key, value, owner: workspaceOwnerSession(),
      timer: setTimeout(() => {
        const w = pending.current;
        pending.current = null;
        if (w) writeAgentDraft(w.key, w.value, w.owner);
      }, DRAFT_DEBOUNCE_MS),
    };
  }, [key]);

  return [draft, setDraft];
}
