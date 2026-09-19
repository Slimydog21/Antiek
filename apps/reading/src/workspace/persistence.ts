/**
 * Closed workspace preferences and retirement of pre-checkpoint layout state.
 *
 * Arbitrary panel descriptors are never read or written here. The only
 * surviving workspace-prefixed record is the closed custom-hotkey envelope.
 */

import {
  detectConflict,
  normalizeBinding,
  requiresModifierReason,
  SAFE_ASSIGNABLE,
} from "../components/hotkeys/bindings";

const LS_PREFIX = "antiek.workspace.";
const LEGACY_GLOBAL_KEY = `${LS_PREFIX}global`;
const LEGACY_ROUTE_PREFIX = `${LS_PREFIX}route.`;
const LEGACY_INVESTIGATION_PREFIX = `${LS_PREFIX}inv.`;
const CUSTOM_HOTKEYS_KEY = `${LS_PREFIX}custom-hotkeys`;

function isLegacyLayoutKey(key: string): boolean {
  return (
    key === LEGACY_GLOBAL_KEY ||
    key.startsWith(LEGACY_ROUTE_PREFIX) ||
    key.startsWith(LEGACY_INVESTIGATION_PREFIX)
  );
}

function isWsQuerySegment(segment: string): boolean {
  const rawName = segment.split("=", 1)[0];
  try {
    return decodeURIComponent(rawName.replace(/\+/g, " ")) === "ws";
  } catch {
    return rawName === "ws";
  }
}

/**
 * Delete only retired panel-layout keys and strip every `ws` query value.
 *
 * Neither operation is a precondition for starting from empty in-memory
 * state: storage/history failures therefore cannot revive legacy authority.
 */
export function retireLegacyWorkspaceSnapshots(): void {
  if (typeof window === "undefined") return;

  try {
    const keys: string[] = [];
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (key && isLegacyLayoutKey(key)) keys.push(key);
    }
    for (const key of keys) window.localStorage.removeItem(key);
  } catch {
    // Fail closed: callers never read or apply a legacy value.
  }

  try {
    const rawSearch = window.location.search.slice(1);
    const segments = rawSearch.split("&");
    if (!segments.some(isWsQuerySegment)) return;
    const search = segments.filter((segment) => !isWsQuerySegment(segment)).join("&");
    window.history.replaceState(
      window.history.state,
      "",
      `${window.location.pathname}${search ? `?${search}` : ""}${window.location.hash}`,
    );
  } catch {
    // URL cleanup failure still cannot make the opaque value executable.
  }
}

/** One persisted custom binding: a hotkey bound to one specific entity. */
export interface PersistedCustomHotkey {
  id: string;
  spec: string;
  route: string;
  entityId: string;
  entityKind: "investigation" | "document" | "deliverable" | "project" | "mode";
  label: string;
}

export interface PersistedCustomHotkeys {
  schemaVersion: 1;
  bindings: PersistedCustomHotkey[];
}

const EMPTY_CUSTOM_HOTKEYS: PersistedCustomHotkeys = {
  schemaVersion: 1,
  bindings: [],
};

const HOTKEY_FIELDS = ["id", "spec", "route", "entityId", "entityKind", "label"] as const;
const ENTITY_KINDS = new Set<PersistedCustomHotkey["entityKind"]>([
  "investigation",
  "document",
  "deliverable",
  "project",
  "mode",
]);
const MAX_BINDINGS = 100;
const MAX_ID_LENGTH = 256;
const MAX_SPEC_LENGTH = 64;
const MAX_ROUTE_LENGTH = 2_048;
const MAX_LABEL_LENGTH = 512;

function hasExactKeys(value: object, expected: readonly string[]): boolean {
  const keys = Object.keys(value);
  return keys.length === expected.length && keys.every((key) => expected.includes(key));
}

function boundedString(value: unknown, maxLength: number): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= maxLength;
}

function isCustomHotkey(value: unknown): value is PersistedCustomHotkey {
  if (typeof value !== "object" || value === null || !hasExactKeys(value, HOTKEY_FIELDS)) {
    return false;
  }
  const binding = value as Record<string, unknown>;
  if (!(
    boundedString(binding.id, MAX_ID_LENGTH) &&
    boundedString(binding.spec, MAX_SPEC_LENGTH) &&
    boundedString(binding.route, MAX_ROUTE_LENGTH) &&
    binding.route.startsWith("/") &&
    boundedString(binding.entityId, MAX_ID_LENGTH) &&
    typeof binding.entityKind === "string" &&
    ENTITY_KINDS.has(binding.entityKind as PersistedCustomHotkey["entityKind"]) &&
    boundedString(binding.label, MAX_LABEL_LENGTH)
  )) return false;
  const spec = normalizeBinding(binding.spec as string);
  return (
    spec === binding.spec &&
    requiresModifierReason(spec) === null &&
    SAFE_ASSIGNABLE.isWithinRange(spec) &&
    detectConflict(spec, []) === null
  );
}

function isCustomHotkeysEnvelope(value: unknown): value is PersistedCustomHotkeys {
  if (
    typeof value !== "object" ||
    value === null ||
    !hasExactKeys(value, ["schemaVersion", "bindings"])
  ) {
    return false;
  }
  const envelope = value as Record<string, unknown>;
  if (!(
    envelope.schemaVersion === 1 &&
    Array.isArray(envelope.bindings) &&
    envelope.bindings.length <= MAX_BINDINGS &&
    envelope.bindings.every(isCustomHotkey)
  )) return false;
  const bindings = envelope.bindings as PersistedCustomHotkey[];
  return (
    new Set(bindings.map((binding) => binding.id)).size === bindings.length &&
    new Set(bindings.map((binding) => binding.spec)).size === bindings.length &&
    new Set(bindings.map((binding) => binding.entityId)).size === bindings.length
  );
}

export function readCustomHotkeys(): PersistedCustomHotkeys {
  if (typeof window === "undefined") return { ...EMPTY_CUSTOM_HOTKEYS };
  try {
    const raw = window.localStorage.getItem(CUSTOM_HOTKEYS_KEY);
    if (!raw) return { ...EMPTY_CUSTOM_HOTKEYS };
    const parsed: unknown = JSON.parse(raw);
    return isCustomHotkeysEnvelope(parsed) ? parsed : { ...EMPTY_CUSTOM_HOTKEYS };
  } catch {
    return { ...EMPTY_CUSTOM_HOTKEYS };
  }
}

export function writeCustomHotkeys(blob: PersistedCustomHotkeys): void {
  if (typeof window === "undefined" || !isCustomHotkeysEnvelope(blob)) return;
  try {
    window.localStorage.setItem(CUSTOM_HOTKEYS_KEY, JSON.stringify(blob));
  } catch {
    // Storage is optional; the same-tab binding remains live in memory.
  }
}

export function clearCustomHotkeys(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(CUSTOM_HOTKEYS_KEY);
  } catch {
    // Storage is optional.
  }
}
