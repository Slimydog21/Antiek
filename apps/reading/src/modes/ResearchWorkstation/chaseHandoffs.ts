import { accountStorageKey } from "../../lib/accountWorkspaceOwner";
import { useEffect, useState } from "react";

export const CHASE_HANDOFFS_EVENT = "antiek:chase-handoffs-changed";
const STORAGE_KEY = "antiek.chase.draftHandoffs.v1";
const memoryHandoffs = new Map<string, ChaseDraftHandoff[]>();

export type ChaseDraftHandoff = {
  kind: "antiek.chase.draft_handoff";
  child_investigation_id: string;
  parent_investigation_id: string;
  source_passage: string;
  next_step: string;
  no_spend: true;
  created_at: string;
};

export function buildChaseDraftHandoff(args: {
  childInvestigationId: string;
  parentInvestigationId: string;
  sourcePassage: string;
}): ChaseDraftHandoff {
  return {
    kind: "antiek.chase.draft_handoff",
    child_investigation_id: args.childInvestigationId,
    parent_investigation_id: args.parentInvestigationId,
    source_passage: args.sourcePassage,
    next_step: "export the child research artifact, then compose it with its parent before merging into the source asset",
    no_spend: true,
    created_at: new Date().toISOString(),
  };
}

export function listChaseDraftHandoffs(parentInvestigationId?: string): ChaseDraftHandoff[] {
  const all = readAll();
  return parentInvestigationId
    ? all.filter((handoff) => handoff.parent_investigation_id === parentInvestigationId)
    : all;
}

export function recordChaseDraftHandoff(handoff: ChaseDraftHandoff): void {
  const current = readAll();
  const next = [
    handoff,
    ...current.filter(
      (item) =>
        !(
          item.child_investigation_id === handoff.child_investigation_id &&
          item.parent_investigation_id === handoff.parent_investigation_id
        ),
    ),
  ].slice(0, 100);
  writeAll(next);
  dispatchChanged();
}

export function clearChaseDraftHandoffs(): void {
  writeAll([]);
  dispatchChanged();
}

export function useChaseDraftHandoffs(parentInvestigationId: string): ChaseDraftHandoff[] {
  const [handoffs, setHandoffs] = useState<ChaseDraftHandoff[]>(() =>
    listChaseDraftHandoffs(parentInvestigationId),
  );

  useEffect(() => {
    const refresh = () => setHandoffs(listChaseDraftHandoffs(parentInvestigationId));
    refresh();
    window.addEventListener(CHASE_HANDOFFS_EVENT, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(CHASE_HANDOFFS_EVENT, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, [parentInvestigationId]);

  return handoffs;
}

function readAll(): ChaseDraftHandoff[] {
  const key = accountStorageKey(STORAGE_KEY);
  if (key === null) return [];
  const cached = memoryHandoffs.get(key) ?? [];
  if (typeof window === "undefined") return cached;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return cached;
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return cached;
    const handoffs = parsed.filter(isHandoff);
    memoryHandoffs.set(key, handoffs);
    return handoffs;
  } catch { return cached; }
}

function writeAll(handoffs: ChaseDraftHandoff[]): void {
  const key = accountStorageKey(STORAGE_KEY);
  if (key === null) return;
  memoryHandoffs.set(key, handoffs);
  if (typeof window === "undefined") return;
  try { window.localStorage.setItem(key, JSON.stringify(handoffs)); }
  catch { /* The same owner's memory copy remains available. */ }
}

function dispatchChanged(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(CHASE_HANDOFFS_EVENT));
}

function isHandoff(value: unknown): value is ChaseDraftHandoff {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return (
    record.kind === "antiek.chase.draft_handoff" &&
    typeof record.child_investigation_id === "string" &&
    typeof record.parent_investigation_id === "string" &&
    typeof record.source_passage === "string" &&
    record.no_spend === true
  );
}
