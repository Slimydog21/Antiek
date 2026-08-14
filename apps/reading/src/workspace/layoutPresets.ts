/**
 * layoutPresets.ts — named, operator-saved workspace layouts (herdr transfer
 * P2, strategy 11). The workspace already persists per-route/investigation
 * layouts; presets are the EXPLICIT named kind — save the current snapshot
 * under a name, apply it anywhere, delete it when stale.
 *
 * Stored in localStorage (versioned key) as a list of PersistedSnapshot
 * objects + metadata; apply reuses the same merge path hydration uses
 * (persistence.applyOver), so a preset can never produce a shape hydration
 * would reject.
 */
import { applyOver, type PersistedSnapshot } from "./persistence";
import { useWorkspace } from "./WorkspaceStore";
import { EMPTY_SNAPSHOT } from "./panel.types";

const KEY = "antiek:layout_presets:v1";

export interface LayoutPreset {
  name: string;
  snapshot: PersistedSnapshot;
  savedAt: string;
}

function readAll(): LayoutPreset[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (p): p is LayoutPreset =>
        p !== null &&
        typeof p === "object" &&
        typeof (p as LayoutPreset).name === "string" &&
        typeof (p as LayoutPreset).snapshot === "object",
    );
  } catch {
    return [];
  }
}

function writeAll(presets: LayoutPreset[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(presets));
  } catch {
    // Quota/private-mode — presets degrade to empty; saving is the only
    // lossy direction, so fail quiet.
  }
}

export function listLayoutPresets(): LayoutPreset[] {
  return readAll();
}

/** Save the CURRENT workspace snapshot under a name (replaces on clash). */
export function saveLayoutPreset(
  name: string,
  snapshot: PersistedSnapshot,
): LayoutPreset {
  const trimmed = name.trim();
  if (!trimmed) throw new Error("preset name must not be empty");
  const presets = readAll().filter((p) => p.name !== trimmed);
  const preset: LayoutPreset = {
    name: trimmed,
    snapshot,
    savedAt: new Date().toISOString(),
  };
  writeAll([preset, ...presets]);
  return preset;
}

export function deleteLayoutPreset(name: string): void {
  writeAll(readAll().filter((p) => p.name !== name));
}

/** Apply a preset: merge over EMPTY_SNAPSHOT and replace store state (the
 *  persistence subscriber writes it to the current scope). */
export function applyLayoutPreset(name: string): boolean {
  const preset = readAll().find((p) => p.name === name);
  if (!preset) return false;
  useWorkspace.setState({
    ...applyOver(EMPTY_SNAPSHOT, preset.snapshot),
    zoomedPanelId: null,
  });
  return true;
}
