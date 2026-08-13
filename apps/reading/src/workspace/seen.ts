/**
 * seen.ts — last-seen timestamps for investigations (herdr transfer, P0-3).
 *
 * The unread flag for research: a completed investigation you have not
 * opened reads "done" with the unread axis (see shared/researchState.ts
 * `isUnseen`). One timestamp per investigation, persisted in localStorage
 * beside the workspace persistence scopes (workspace/persistence.ts) —
 * deliberately NOT in the workspace snapshot: seen-state is per-operator
 * attention, not per-layout.
 *
 * Storage key is versioned so a future shape change can migrate rather
 * than silently corrupt. SSR-safe (guard `window`).
 */
const KEY = "antiek:last_seen:v1";

export type SeenMap = Record<string, string>;

function read(): SeenMap {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as SeenMap;
    }
    return {};
  } catch {
    return {};
  }
}

function write(map: SeenMap): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(map));
  } catch {
    // Quota/private-mode — seen-state degrades to "always unread", which is
    // the honest direction (better a false unread than a false read).
  }
}

/** ISO timestamp of the last time the operator opened this investigation,
 *  or null when never seen. */
export function lastSeenAt(investigationId: string): string | null {
  return read()[investigationId] ?? null;
}

/** Record "the operator looked at this investigation, now". */
export function markSeen(investigationId: string): void {
  if (!investigationId) return;
  const map = read();
  map[investigationId] = new Date().toISOString();
  write(map);
}

/** All seen timestamps (for bulk reads like the palette index). */
export function allSeen(): SeenMap {
  return read();
}
