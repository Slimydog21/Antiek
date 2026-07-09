/**
 * recentDeepResearchSpawns — session-scoped ring of deep-research spawn ids.
 *
 * Residual (ob): after twin chase / floating DR open, keep spawn ids available
 * for CollectiveResearchPanel multi-select even if the operator closes the
 * floating window. Pure sessionStorage; no network; no invented ids.
 *
 * Max length is bounded so dogfood sessions cannot grow unboundedly.
 */

export const RECENT_DEEP_RESEARCH_SPAWNS_KEY = "antiek.dr.recent_spawn_ids";
export const RECENT_DEEP_RESEARCH_SPAWNS_MAX = 24;

function readRaw(): string[] {
  if (typeof window === "undefined" || !window.sessionStorage) return [];
  try {
    const raw = window.sessionStorage.getItem(RECENT_DEEP_RESEARCH_SPAWNS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((x) => String(x ?? "").trim())
      .filter(Boolean);
  } catch {
    return [];
  }
}

function writeRaw(ids: string[]): void {
  if (typeof window === "undefined" || !window.sessionStorage) return;
  try {
    window.sessionStorage.setItem(
      RECENT_DEEP_RESEARCH_SPAWNS_KEY,
      JSON.stringify(ids.slice(0, RECENT_DEEP_RESEARCH_SPAWNS_MAX)),
    );
  } catch {
    /* quota / private mode — non-fatal */
  }
}

/** List recent spawn ids (newest first). */
export function listRecentDeepResearchSpawnIds(): string[] {
  return readRaw();
}

/**
 * Push a spawn id to the front of the recent ring (dedupe, max cap).
 * Empty/whitespace ids are ignored (never invent).
 */
export function pushRecentDeepResearchSpawnId(spawnId: string): string[] {
  const id = (spawnId || "").trim();
  if (!id) return listRecentDeepResearchSpawnIds();
  const prev = readRaw().filter((x) => x !== id);
  const next = [id, ...prev].slice(0, RECENT_DEEP_RESEARCH_SPAWNS_MAX);
  writeRaw(next);
  return next;
}

/** Test / dogfood reset. */
export function clearRecentDeepResearchSpawnIds(): void {
  if (typeof window === "undefined" || !window.sessionStorage) return;
  try {
    window.sessionStorage.removeItem(RECENT_DEEP_RESEARCH_SPAWNS_KEY);
  } catch {
    /* non-fatal */
  }
}
