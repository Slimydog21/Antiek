/**
 * Workspace persistence — S9.
 *
 * Three scopes, layered at hydration time:
 *
 *   1. Global         antiek.workspace.global       (route-agnostic shell)
 *   2. Route          antiek.workspace.route.<key>  (per-route preferred layout)
 *   3. Investigation  antiek.workspace.inv.<id>     (overrides for a specific inv)
 *
 * Plus the URL ?ws=<base64-json> param wins over all three at load time.
 *
 * What we store:
 *   - panels (the descriptors map)
 *   - dock arrays (left/right/bottom)
 *   - dockBottomHeight
 *   - schemaVersion (for forward-compat migrations)
 *
 * What we STRIP (transient — never write to disk):
 *   - focusedPanelId
 *   - zCounter (re-derived at hydration: max(panels.zIndex) + 1)
 *   - floatingIds order (re-derived: order of floating panels by zIndex)
 *
 * Schema-version mismatch at hydration → log + ignore the snapshot.
 */

import type { WorkspaceSnapshot } from "./panel.types";

const LS_PREFIX = "antiek.workspace.";

/** What gets serialised to disk. Strict subset of WorkspaceSnapshot. */
export type PersistedSnapshot = {
  schemaVersion: 1;
  panels: WorkspaceSnapshot["panels"];
  dockLeftIds: string[];
  dockRightIds: string[];
  dockBottomIds: string[];
  dockBottomHeight: number;
};

export type PersistScope =
  | { kind: "global" }
  | { kind: "route"; route: string }
  | { kind: "investigation"; id: string };

function lsKey(scope: PersistScope): string {
  if (scope.kind === "global") return LS_PREFIX + "global";
  if (scope.kind === "route") return LS_PREFIX + "route." + scope.route;
  return LS_PREFIX + "inv." + scope.id;
}

/** Strip transient fields. */
export function project(snapshot: WorkspaceSnapshot): PersistedSnapshot {
  return {
    schemaVersion: 1,
    panels: snapshot.panels,
    dockLeftIds: snapshot.dockLeftIds,
    dockRightIds: snapshot.dockRightIds,
    dockBottomIds: snapshot.dockBottomIds,
    dockBottomHeight: snapshot.dockBottomHeight,
  };
}

/** Merge a persisted snapshot over a base snapshot. Newer entries
 *  win on conflicting ids. Returns a full WorkspaceSnapshot. */
export function applyOver(
  base: WorkspaceSnapshot,
  layer: PersistedSnapshot,
): WorkspaceSnapshot {
  if (layer.schemaVersion !== 1) {
    if (typeof console !== "undefined") {
      // eslint-disable-next-line no-console
      console.warn(
        "[antiek/persistence] ignoring snapshot with mismatched schemaVersion:",
        layer.schemaVersion,
      );
    }
    return base;
  }
  // Union the panel descriptors; layer wins on duplicate ids.
  const panels = { ...base.panels, ...layer.panels };

  // Replace the dock arrays with the layer's (operator's intent on this scope).
  const dockLeftIds = layer.dockLeftIds ?? base.dockLeftIds;
  const dockRightIds = layer.dockRightIds ?? base.dockRightIds;
  const dockBottomIds = layer.dockBottomIds ?? base.dockBottomIds;

  // Re-derive floatingIds from the union: any panel whose mode is "floating".
  const floatingIds = Object.values(panels)
    .filter((p) => p.mode === "floating")
    .sort((a, b) => a.zIndex - b.zIndex)
    .map((p) => p.id);

  // Re-derive zCounter so the next floating panel sits on top.
  const maxZ = Object.values(panels).reduce(
    (acc, p) => Math.max(acc, p.zIndex),
    0,
  );

  return {
    ...base,
    panels,
    dockLeftIds,
    dockRightIds,
    dockBottomIds,
    floatingIds,
    zCounter: maxZ,
    dockBottomHeight: layer.dockBottomHeight ?? base.dockBottomHeight,
    focusedPanelId: null,
    schemaVersion: 1,
  };
}

/** Read a snapshot from localStorage. Returns null on miss / parse error. */
export function readScope(scope: PersistScope): PersistedSnapshot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(lsKey(scope));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedSnapshot;
    if (typeof parsed !== "object" || parsed === null) return null;
    return parsed;
  } catch {
    return null;
  }
}

/** Write a snapshot to localStorage. Silent on quota errors. */
export function writeScope(scope: PersistScope, snapshot: PersistedSnapshot): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(lsKey(scope), JSON.stringify(snapshot));
  } catch {
    // Quota exceeded or storage disabled — silent fail; the workspace
    // continues to function in-memory.
  }
}

/** Delete a scope's stored snapshot. */
export function clearScope(scope: PersistScope): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(lsKey(scope));
  } catch {
    // ignore
  }
}

/** Delete every antiek.workspace.* key. Used by the "reset all layouts"
 *  palette command. Returns the count of keys removed. */
export function clearAll(): number {
  if (typeof window === "undefined") return 0;
  let count = 0;
  try {
    const keys: string[] = [];
    for (let i = 0; i < window.localStorage.length; i++) {
      const k = window.localStorage.key(i);
      if (k && k.startsWith(LS_PREFIX)) keys.push(k);
    }
    for (const k of keys) {
      window.localStorage.removeItem(k);
      count++;
    }
  } catch {
    // ignore
  }
  return count;
}

// ─────────────────────────────────────────────────────────────────────
// URL shareable snapshot — ?ws=<base64-json>
// ─────────────────────────────────────────────────────────────────────

/** Encode a snapshot to a base64-JSON string suitable for ?ws=. */
export function encodeWsParam(snapshot: PersistedSnapshot): string {
  const json = JSON.stringify(snapshot);
  // unescape(encodeURIComponent) → UTF-8 safe btoa
  return btoa(unescape(encodeURIComponent(json)));
}

/** Decode a base64-JSON ?ws= value. Returns null on parse error. */
export function decodeWsParam(raw: string): PersistedSnapshot | null {
  try {
    const json = decodeURIComponent(escape(atob(raw)));
    const parsed = JSON.parse(json) as PersistedSnapshot;
    if (typeof parsed !== "object" || parsed === null) return null;
    if (parsed.schemaVersion !== 1) return null;
    return parsed;
  } catch {
    return null;
  }
}

/** Read + decode the current URL's `?ws=` param, if present. */
export function readWsFromUrl(): PersistedSnapshot | null {
  if (typeof window === "undefined") return null;
  const usp = new URLSearchParams(window.location.search);
  const raw = usp.get("ws");
  if (!raw) return null;
  return decodeWsParam(raw);
}

/** Strip the `ws=` query param from the current URL without a reload. */
export function clearWsFromUrl(): void {
  if (typeof window === "undefined") return;
  const usp = new URLSearchParams(window.location.search);
  if (!usp.has("ws")) return;
  usp.delete("ws");
  const search = usp.toString();
  const next =
    window.location.pathname +
    (search ? "?" + search : "") +
    window.location.hash;
  window.history.replaceState({}, "", next);
}

/** Build a shareable URL for the current workspace state. */
export function buildShareableUrl(snapshot: PersistedSnapshot): string {
  if (typeof window === "undefined") return "";
  const usp = new URLSearchParams(window.location.search);
  usp.set("ws", encodeWsParam(snapshot));
  return (
    window.location.origin +
    window.location.pathname +
    "?" +
    usp.toString() +
    window.location.hash
  );
}

// ─────────────────────────────────────────────────────────────────────
// Custom hotkeys — SPR-08 (ADDITIVE: a SEPARATE global-scoped, versioned
// blob, deliberately NOT folded into the layout PersistedSnapshot)
// ─────────────────────────────────────────────────────────────────────
//
// Rationale for a separate blob (not a new field on PersistedSnapshot):
// custom hotkeys are global + route-agnostic + low-churn, whereas the
// layout snapshot is per-scope + high-churn (every panel move debounces a
// write). Coupling them would (a) rewrite the hotkey map on every layout
// tweak and (b) scatter the same hotkey map across the global/route/inv
// scope keys. One global key, its own schemaVersion, owned by the hotkey
// system. Stored at `antiek.workspace.custom-hotkeys`.

const CUSTOM_HOTKEYS_KEY = LS_PREFIX + "custom-hotkeys";

/** One persisted custom binding: a hotkey bound to ONE specific entity. */
export interface PersistedCustomHotkey {
  /** Stable id for this binding (uuid-ish). */
  id: string;
  /** Canonical ⌘+key combo spec, e.g. "mod+j" or "alt+j" (never a chord). */
  spec: string;
  /**
   * Route TEMPLATE the entity lives on, with the param already substituted,
   * e.g. "/inv/abc123" or "/read/doc-9". Stored fully-resolved so a press
   * navigates deterministically without re-deriving the template.
   */
  route: string;
  /** The bound entity id (investigationId / documentId / deliverableId / projectId). */
  entityId: string;
  /** Entity kind, for the HUD/affordance label. */
  entityKind: "investigation" | "document" | "deliverable" | "project" | "mode";
  /** Operator-readable label for the HUD (e.g. the investigation title). */
  label: string;
}

/** The versioned envelope written to localStorage. */
export interface PersistedCustomHotkeys {
  schemaVersion: 1;
  bindings: PersistedCustomHotkey[];
}

const EMPTY_CUSTOM_HOTKEYS: PersistedCustomHotkeys = {
  schemaVersion: 1,
  bindings: [],
};

/** Read the custom-hotkeys blob. Returns an empty (v1) envelope on miss,
 *  parse error, or schema-version mismatch (forward-compat: ignore + log). */
export function readCustomHotkeys(): PersistedCustomHotkeys {
  if (typeof window === "undefined") return { ...EMPTY_CUSTOM_HOTKEYS };
  try {
    const raw = window.localStorage.getItem(CUSTOM_HOTKEYS_KEY);
    if (!raw) return { ...EMPTY_CUSTOM_HOTKEYS };
    const parsed = JSON.parse(raw) as PersistedCustomHotkeys;
    if (typeof parsed !== "object" || parsed === null) {
      return { ...EMPTY_CUSTOM_HOTKEYS };
    }
    if (parsed.schemaVersion !== 1) {
      if (typeof console !== "undefined") {
        // eslint-disable-next-line no-console
        console.warn(
          "[antiek/persistence] ignoring custom-hotkeys with mismatched schemaVersion:",
          parsed.schemaVersion,
        );
      }
      return { ...EMPTY_CUSTOM_HOTKEYS };
    }
    if (!Array.isArray(parsed.bindings)) return { ...EMPTY_CUSTOM_HOTKEYS };
    return parsed;
  } catch {
    return { ...EMPTY_CUSTOM_HOTKEYS };
  }
}

/** Write the custom-hotkeys blob. Silent on quota errors. */
export function writeCustomHotkeys(blob: PersistedCustomHotkeys): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      CUSTOM_HOTKEYS_KEY,
      JSON.stringify({ schemaVersion: 1, bindings: blob.bindings }),
    );
  } catch {
    // Quota exceeded / storage disabled — silent; in-memory state stands.
  }
}

/** Delete the custom-hotkeys blob (reset-to-defaults). */
export function clearCustomHotkeys(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(CUSTOM_HOTKEYS_KEY);
  } catch {
    // ignore
  }
}
