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

import { isFeatureOn } from "../lib/featureFlags";
import type { WorkspaceSnapshot } from "./panel.types";
import type { LayoutPreset } from "./panel.types";
import { accountStorageKey, workspaceOwnerSession } from "../lib/accountWorkspaceOwner";
import type { PaneArrangement, PaneTarget, PaneTile } from "./panel.types";
import {
  ARRANGEMENT_SLOTS,
  isArrangementSlot,
  type ArrangementPreset,
  type PaneArrangementMap,
  type ProjectSlots,
} from "./paneArrangements";
import { replaceNavigationStateWithoutPublication } from "./navigationLifetime";

const LS_PREFIX = "antiek.workspace.";

/** What gets serialised to disk. Strict subset of WorkspaceSnapshot. */
export type PersistedSnapshot = {
  schemaVersion: 1;
  ownerSubject?: string;
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

function lsKey(scope: PersistScope): string | null {
  const suffix = scope.kind === "global" ? "global"
    : scope.kind === "route" ? "route." + scope.route : "inv." + scope.id;
  return accountStorageKey(LS_PREFIX + suffix);
}

/** Strip transient fields. */
export function project(snapshot: WorkspaceSnapshot): PersistedSnapshot {
  const subject = workspaceOwnerSession().subject;
  return {
    schemaVersion: 1,
    ...(subject === null ? {} : { ownerSubject: subject }),
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
  const key = lsKey(scope);
  if (key === null) return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedSnapshot;
    if (typeof parsed !== "object" || parsed === null) return null;
    if (parsed.ownerSubject !== workspaceOwnerSession().subject) return null;
    return parsed;
  } catch {
    return null;
  }
}

/** Write a snapshot to localStorage. Silent on quota errors. */
export function writeScope(scope: PersistScope, snapshot: PersistedSnapshot): void {
  if (typeof window === "undefined") return;
  const key = lsKey(scope);
  if (key === null) return;
  if (snapshot.ownerSubject !== workspaceOwnerSession().subject) return;
  try {
    window.localStorage.setItem(key, JSON.stringify(snapshot));
  } catch {
    // Quota exceeded or storage disabled — silent fail; the workspace
    // continues to function in-memory.
  }
}

/** Delete a scope's stored snapshot. */
export function clearScope(scope: PersistScope): void {
  if (typeof window === "undefined") return;
  const key = lsKey(scope);
  if (key === null) return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

/** Delete every antiek.workspace.* key. Used by the "reset all layouts"
 *  palette command. Returns the count of keys removed. */
export function clearAll(): number {
  if (typeof window === "undefined") return 0;
  const ownerSuffix = accountStorageKey("");
  if (ownerSuffix === null) return 0;
  let count = 0;
  try {
    const keys: string[] = [];
    for (let i = 0; i < window.localStorage.length; i++) {
      const k = window.localStorage.key(i);
      if (k && k.startsWith(LS_PREFIX) && k.endsWith(ownerSuffix)) keys.push(k);
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
  const snapshot = decodeWsParam(raw);
  const owner = workspaceOwnerSession().subject;
  return owner !== null && snapshot?.ownerSubject === owner ? snapshot : null;
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
  // Landing: the packet routes this native replacement through
  // navigationLifetime so the navigation epoch advances without a router
  // publication (navigationLifetime.test: "removes ws through exactly the
  // original native replacement"). The import had landed; this call had not.
  replaceNavigationStateWithoutPublication({}, next);
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
  const key = accountStorageKey(CUSTOM_HOTKEYS_KEY);
  if (key === null) return { ...EMPTY_CUSTOM_HOTKEYS };
  try {
    const raw = window.localStorage.getItem(key);
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
  const key = accountStorageKey(CUSTOM_HOTKEYS_KEY);
  if (key === null) return;
  try {
    window.localStorage.setItem(
      key,
      JSON.stringify({ schemaVersion: 1, bindings: blob.bindings }),
    );
  } catch {
    // Quota exceeded / storage disabled — silent; in-memory state stands.
  }
}

/** Delete the custom-hotkeys blob (reset-to-defaults). */
export function clearCustomHotkeys(): void {
  if (typeof window === "undefined") return;
  const key = accountStorageKey(CUSTOM_HOTKEYS_KEY);
  if (key === null) return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

// ─────────────────────────────────────────────────────────────────────
// Layout preset — cockpit chrome C2 (ADDITIVE: a SEPARATE global-scoped,
// versioned blob, deliberately NOT folded into the layout PersistedSnapshot)
// ─────────────────────────────────────────────────────────────────────
//
// Same rationale as custom-hotkeys above: the layout preset is global +
// route-agnostic + low-churn (an operator picks it once), whereas the layout
// snapshot is per-scope + high-churn. Coupling them would rewrite the preset
// into every scope key on every panel move. One global key, its own
// schemaVersion, owned by the cockpit chrome. Stored at
// `antiek.workspace.layout-preset`; absent/invalid reads use the cockpit.
// An explicit stored choice, including docked, survives the default change.

const LAYOUT_PRESET_KEY = LS_PREFIX + "layout-preset";

/** The preset a workspace starts on: no stored value, a parse error, a schema
 *  mismatch or an unknown value all resolve here. ONE name, so anything that
 *  describes the default in prose can be built from it rather than restating
 *  it -- the key sheet did the latter and told the operator the opposite
 *  (PR #3586). */
export const LAYOUT_PRESET_DEFAULT: LayoutPreset = "omarchy-inset";

/** The versioned envelope written to localStorage. */
export interface PersistedLayoutPreset {
  schemaVersion: 1;
  preset: LayoutPreset;
}

/** Read the persisted choice, or the default on missing/invalid storage. */
export function readLayoutPreset(): LayoutPreset {
  if (typeof window === "undefined") return LAYOUT_PRESET_DEFAULT;
  try {
    const raw = window.localStorage.getItem(LAYOUT_PRESET_KEY);
    if (!raw) return LAYOUT_PRESET_DEFAULT;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || !("schemaVersion" in parsed) || parsed.schemaVersion !== 1) {
      if (typeof console !== "undefined") {
        // eslint-disable-next-line no-console
        console.warn(
          "[antiek/persistence] ignoring layout-preset with mismatched schemaVersion:",
          typeof parsed === "object" && parsed !== null && "schemaVersion" in parsed ? parsed.schemaVersion : undefined,
        );
      }
      return LAYOUT_PRESET_DEFAULT;
    }
    return "preset" in parsed && (parsed.preset === "omarchy-inset" || parsed.preset === "docked")
      ? parsed.preset
      : LAYOUT_PRESET_DEFAULT;
  } catch {
    return LAYOUT_PRESET_DEFAULT;
  }
}

/** Write the preset blob. Silent on quota errors. */
export function writeLayoutPreset(preset: LayoutPreset): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      LAYOUT_PRESET_KEY,
      JSON.stringify({ schemaVersion: 1, preset } satisfies PersistedLayoutPreset),
    );
  } catch {
    // Quota exceeded / storage disabled — silent; in-memory state stands.
  }
}

/** Delete the preset blob (back to the default on next load). */
export function clearLayoutPreset(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(LAYOUT_PRESET_KEY);
  } catch {
    // ignore
  }
}

// ─────────────────────────────────────────────────────────────────────
// Selected account project — the D2 project level (ADDITIVE: a SEPARATE
// global-scoped, versioned blob, deliberately NOT folded into the layout
// PersistedSnapshot, for the same reason as the layout preset above)
// ─────────────────────────────────────────────────────────────────────
//
// The tab trees are filed per project (tabTreeStore): the adapter's load
// and save take the project id, so which project is selected decides which
// trees the cockpit shows. The selection itself is global + route-agnostic
// + low-churn operator state, exactly like the layout preset, so it gets
// the same shape: one global key, its own schemaVersion. Stored at
// `antiek.workspace.tab-project`; absent/invalid reads as null, which the
// store reads as the default project, so a stored id never surprises an
// operator who never chose one.

const TAB_PROJECT_KEY = LS_PREFIX + "tab-project";

/** The versioned envelope written to localStorage. */
export interface PersistedTabProject {
  schemaVersion: 1;
  /** The selected write_folders project_id; null is never written (clear
   *  instead), so a stored value is always a real id. */
  projectId: string;
}

/** Read the persisted selection. Null on miss, parse error, version
 *  mismatch, or an empty value — the default project is the failure mode. */
export function readTabProject(): string | null {
  if (typeof window === "undefined") return null;
  const key = accountStorageKey(TAB_PROJECT_KEY);
  if (key === null) return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedTabProject;
    if (typeof parsed !== "object" || parsed === null || parsed.schemaVersion !== 1) {
      if (typeof console !== "undefined") {
        // eslint-disable-next-line no-console
        console.warn(
          "[antiek/persistence] ignoring tab-project with mismatched schemaVersion:",
          (parsed as PersistedTabProject | null)?.schemaVersion,
        );
      }
      return null;
    }
    return typeof parsed.projectId === "string" && parsed.projectId.length > 0
      ? parsed.projectId
      : null;
  } catch {
    return null;
  }
}

/** Write the selection blob. Silent on quota errors. */
export function writeTabProject(projectId: string): void {
  if (typeof window === "undefined") return;
  const key = accountStorageKey(TAB_PROJECT_KEY);
  if (key === null) return;
  try {
    window.localStorage.setItem(
      key,
      JSON.stringify({ schemaVersion: 1, projectId } satisfies PersistedTabProject),
    );
  } catch {
    // Quota exceeded / storage disabled — silent; in-memory state stands.
  }
}

/** Delete the selection blob (back to the default project on next load). */
export function clearTabProject(): void {
  if (typeof window === "undefined") return;
  const key = accountStorageKey(TAB_PROJECT_KEY);
  if (key === null) return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

const DESKTOP_PANE_KEY = LS_PREFIX + "desktop-pane-arrangement.v1";

type PreferenceRead<T> = { kind: "absent" } | { kind: "invalid" } | { kind: "valid"; value: T };

export function parsePaneArrangement(raw: string | null): PreferenceRead<PaneArrangement> {
  if (raw === null) return { kind: "absent" };
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null || !("schemaVersion" in value)
        || value.schemaVersion !== 1 || !("arrangement" in value)) return { kind: "invalid" };
    switch (value.arrangement) {
      case "legacy": case "horizontal": case "tiled": return { kind: "valid", value: value.arrangement };
      default: return { kind: "invalid" };
    }
  } catch { return { kind: "invalid" }; }
}

export function parseLegacyPanePreset(raw: string | null): PreferenceRead<LayoutPreset> {
  if (raw === null) return { kind: "absent" };
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null || !("schemaVersion" in value)
        || value.schemaVersion !== 1 || !("preset" in value)) return { kind: "invalid" };
    switch (value.preset) {
      case "docked": case "omarchy-inset": return { kind: "valid", value: value.preset };
      default: return { kind: "invalid" };
    }
  } catch { return { kind: "invalid" }; }
}

/** A valid old choice stays legacy until the operator chooses the new flow.
 * Fresh/invalid preferences start horizontal with the existing inset mounts.
 * Neither old preset is relabelled as horizontal or tiled. No saved layout
 * snapshot, scope, schema, or preference key is rewritten during the read. */
export function migratePanePreferences(arrangementRaw: string | null, presetRaw: string | null): {
  paneArrangement: PaneArrangement; layoutPreset: LayoutPreset;
} {
  const arrangement = parsePaneArrangement(arrangementRaw);
  const preset = parseLegacyPanePreset(presetRaw);
  if (arrangement.kind === "valid") {
    return { paneArrangement: arrangement.value,
      layoutPreset: preset.kind === "valid" ? preset.value
        : arrangement.value === "legacy" ? "docked" : "omarchy-inset" };
  }
  return preset.kind === "valid"
    ? { paneArrangement: "legacy", layoutPreset: preset.value }
    : { paneArrangement: "horizontal", layoutPreset: "omarchy-inset" };
}

export function readPanePreferences(): { paneArrangement: PaneArrangement; layoutPreset: LayoutPreset } {
  if (typeof window === "undefined") return { paneArrangement: "legacy", layoutPreset: "docked" };
  // Landing gate (antiek.flag.pane.flow, default OFF): with the flag off the
  // arrangement is always legacy and the preset is main's persisted read —
  // nothing a flag-off user sees changes, and no preference is rewritten.
  if (!isFeatureOn("pane.flow")) return { paneArrangement: "legacy", layoutPreset: readLayoutPreset() };
  try {
    return migratePanePreferences(window.localStorage.getItem(DESKTOP_PANE_KEY),
      window.localStorage.getItem(LAYOUT_PRESET_KEY));
  } catch {
    return { paneArrangement: "legacy", layoutPreset: readLayoutPreset() };
  }
}

export function writePaneArrangement(arrangement: PaneArrangement): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.setItem(DESKTOP_PANE_KEY, JSON.stringify({ schemaVersion: 1, arrangement })); }
  catch { /* The current client choice survives unavailable storage. */ }
}

// ─────────────────────────────────────────────────────────────────────
// Numbered pane arrangements — SPR-01 M6 (R11). ADDITIVE: a SEPARATE
// account-scoped, versioned blob, deliberately NOT folded into the layout
// PersistedSnapshot, for the same reason as the layout preset and the tab
// project above: arrangements are chrome preference, not layout state.
// ─────────────────────────────────────────────────────────────────────
//
// One key (`antiek.workspace.pane-arrangements`), one schemaVersion, keyed
// inside by the account project id (project.select's id). The guard is the
// existing rule, applied WHOLE: a missing key reads as no arrangements; a
// parse error, a schemaVersion mismatch, or any structurally invalid entry
// discards the blob ENTIRELY with a warning — never a half-trusted preset.

const PANE_ARRANGEMENTS_KEY = LS_PREFIX + "pane-arrangements";

interface PersistedPaneArrangements {
  schemaVersion: 1;
  projects: PaneArrangementMap;
}

function validTarget(value: unknown): value is PaneTarget {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  if (record.kind === "core" || record.kind === "companion") return true;
  return record.kind === "window" && typeof record.id === "string" && record.id.length > 0;
}

function validTile(value: unknown): value is PaneTile {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  if (record.kind === "leaf") return validTarget(record.target);
  if (record.kind !== "split") return false;
  return (record.axis === "x" || record.axis === "y")
    && typeof record.ratio === "number" && Number.isFinite(record.ratio)
    && validTile(record.first) && validTile(record.second);
}

function validPreset(value: unknown): value is ArrangementPreset {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return (record.arrangement === "horizontal" || record.arrangement === "tiled")
    && Array.isArray(record.order) && record.order.every(validTarget)
    && (record.tiles === null || validTile(record.tiles));
}

function validProjectSlots(value: unknown): value is ProjectSlots {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  if (!isArrangementSlot(record.current)) return false;
  if (record.last !== null && !isArrangementSlot(record.last)) return false;
  if (typeof record.presets !== "object" || record.presets === null) return false;
  return Object.entries(record.presets as Record<string, unknown>).every(([slot, preset]) =>
    (ARRANGEMENT_SLOTS as readonly string[]).includes(slot) && validPreset(preset));
}

/** Read every project's slots. {} on miss; the WHOLE blob is discarded on a
 *  parse error, a version mismatch, or any invalid entry. */
export function readPaneArrangements(): PaneArrangementMap {
  if (typeof window === "undefined") return {};
  const key = accountStorageKey(PANE_ARRANGEMENTS_KEY);
  if (key === null) return {};
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    const valid = typeof parsed === "object" && parsed !== null
      && (parsed as PersistedPaneArrangements).schemaVersion === 1
      && typeof (parsed as PersistedPaneArrangements).projects === "object"
      && (parsed as PersistedPaneArrangements).projects !== null
      && Object.values((parsed as PersistedPaneArrangements).projects).every(validProjectSlots);
    if (!valid) {
      // eslint-disable-next-line no-console
      console.warn("[antiek/persistence] discarding pane-arrangements blob (unknown version or invalid entry)");
      return {};
    }
    return (parsed as PersistedPaneArrangements).projects;
  } catch {
    return {};
  }
}

/** Write the whole map (one blob; arrangement ops are rare). Silent on
 *  quota errors — the in-memory state stands. */
export function writePaneArrangements(projects: PaneArrangementMap): void {
  if (typeof window === "undefined") return;
  const key = accountStorageKey(PANE_ARRANGEMENTS_KEY);
  if (key === null) return;
  try {
    window.localStorage.setItem(key, JSON.stringify({ schemaVersion: 1, projects } satisfies PersistedPaneArrangements));
  } catch {
    // Quota exceeded / storage disabled — silent; in-memory state stands.
  }
}

/** Delete the blob (reset-to-defaults). */
export function clearPaneArrangements(): void {
  if (typeof window === "undefined") return;
  const key = accountStorageKey(PANE_ARRANGEMENTS_KEY);
  if (key === null) return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
}
