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
 * The store is REACTIVE (subscribe/version), so a surface that marks seen
 * re-renders every other surface that displays unread state — the same
 * pub-sub discipline LemonToast uses. Cross-tab writes sync via the
 * `storage` event (last-write-wins; a second tab's mark wins — acceptable
 * for one operator's attention state).
 *
 * Storage key is versioned so a future shape change can migrate rather
 * than silently corrupt. SSR-safe (guard `window`).
 */
const KEY = "antiek:last_seen:v1";

export type SeenMap = Record<string, string>;

let _version = 0;
const _listeners = new Set<() => void>();

function bump(): void {
  _version += 1;
  for (const l of _listeners) l();
}

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
  bump();
}

/** All seen timestamps (for bulk reads like the palette index). */
export function allSeen(): SeenMap {
  return read();
}

/** Current store version — changes on every markSeen or cross-tab write.
 *  Surfaces call this from useSeenVersion() to re-render on change. */
export function getSeenVersion(): number {
  return _version;
}

/** Subscribe to seen-state changes. Returns an unsubscribe fn. */
export function subscribeSeen(listener: () => void): () => void {
  _listeners.add(listener);
  if (typeof window !== "undefined") {
    const onStorage = (e: StorageEvent) => {
      if (e.key === KEY) bump();
    };
    window.addEventListener("storage", onStorage);
    return () => {
      _listeners.delete(listener);
      window.removeEventListener("storage", onStorage);
    };
  }
  return () => {
    _listeners.delete(listener);
  };
}
