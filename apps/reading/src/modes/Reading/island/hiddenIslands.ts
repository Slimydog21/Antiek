/**
 * hiddenIslands.ts — the operator-chosen "hide" view preference (island
 * SPR-02). A hide is a CLIENT-SIDE, PER-DEVICE preference keyed by anchor id
 * — it never deletes the anchor, the thread, or the link (those are the
 * unit-1 stores' truth; this only changes what THIS device paints). Session
 * dismissal (the card's Dismiss) is separate and lives in component state;
 * this is the persistent per-device variant, stored as a small versioned
 * localStorage blob following the custom-hotkeys / layout-preset precedent
 * (one global key, its own schemaVersion).
 */

const HIDDEN_ISLANDS_KEY = "antiek.island.hidden";

export const HIDDEN_ISLANDS_CHANGED = "antiek:island-hidden-changed";

interface HiddenIslandsBlob {
  schemaVersion: 1;
  anchorIds: string[];
}

export function readHiddenIslands(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage.getItem(HIDDEN_ISLANDS_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as HiddenIslandsBlob;
    if (typeof parsed !== "object" || parsed === null || parsed.schemaVersion !== 1) {
      return new Set();
    }
    return new Set(Array.isArray(parsed.anchorIds) ? parsed.anchorIds : []);
  } catch {
    return new Set();
  }
}

function write(set: Set<string>): void {
  if (typeof window === "undefined") return;
  try {
    const blob: HiddenIslandsBlob = { schemaVersion: 1, anchorIds: [...set].sort() };
    window.localStorage.setItem(HIDDEN_ISLANDS_KEY, JSON.stringify(blob));
    window.dispatchEvent(new Event(HIDDEN_ISLANDS_CHANGED));
  } catch {
    // Storage unavailable — the hide simply doesn't persist; in-memory
    // state stands (never a crash for a view preference).
  }
}

export function hideIsland(anchorId: string): void {
  const set = readHiddenIslands();
  set.add(anchorId);
  write(set);
}

export function unhideIsland(anchorId: string): void {
  const set = readHiddenIslands();
  set.delete(anchorId);
  write(set);
}
