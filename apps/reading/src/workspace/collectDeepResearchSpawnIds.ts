/**
 * collectDeepResearchSpawnIds — pure handoff for CollectiveResearchPanel.
 *
 * Builds the multi-select spawn list from:
 *   1. current session spawn_id (when present)
 *   2. optional extra spawn ids (props)
 *   3. open windows of kind deep_research_session (payload.spawn_id)
 *   4. Residual (ob): recent session-scoped spawn ids (closed windows still
 *      mergeable for twin-chase → collective cohesive unit path)
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
  /**
   * Residual (ob): recent spawn ids from sessionStorage ring
   * (twin chase / floating DR opens that may already be closed).
   */
  recentSpawnIds?: readonly string[] | null;
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

  // Residual (ob): closed-window chase/float spawns still available for merge.
  for (const recent of source.recentSpawnIds ?? []) {
    push(recent);
  }

  return out;
}
