/**
 * collectDeepResearchSpawnIds — pure handoff for CollectiveResearchPanel.
 *
 * Builds the multi-select spawn list from:
 *   1. current session spawn_id (when present)
 *   2. open windows of kind deep_research_session (payload.spawn_id)
 *
 * Does not invent ids; does not call the collective API.
 */

import { DEEP_RESEARCH_WINDOW_KIND } from "./deepResearchWindow";
import type { WorkspaceWindowDescriptor } from "./windowsStore";

export type SpawnIdSource = {
  /** Current host session spawn (if any). */
  currentSpawnId?: string | null;
  /** Optional extra spawn ids (e.g. from props). */
  extraSpawnIds?: readonly string[] | null;
  /** Open workspace windows (from windowsStore). */
  windows?: Record<string, WorkspaceWindowDescriptor> | null;
};

/** Stable unique list of non-empty spawn ids for collective multi-select. */
export function collectDeepResearchSpawnIds(source: SpawnIdSource): string[] {
  const seen = new Set<string>();
  const out: string[] = [];

  const push = (raw: unknown) => {
    if (typeof raw !== "string") return;
    const id = raw.trim();
    if (!id || seen.has(id)) return;
    seen.add(id);
    out.push(id);
  };

  push(source.currentSpawnId);
  for (const extra of source.extraSpawnIds ?? []) {
    push(extra);
  }

  const windows = source.windows ?? {};
  for (const win of Object.values(windows)) {
    if (!win || win.kind !== DEEP_RESEARCH_WINDOW_KIND) continue;
    const payload = win.payload ?? {};
    push(payload.spawn_id);
  }

  return out;
}
