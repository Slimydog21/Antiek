// SPR-07 M7 — User settings (per-operator).
//
// At SPR-07 closeout the only setting that lives here is the
// public-graph cross-doc toggle. The store is intentionally tiny — a
// localStorage-backed Zustand store — so a future SettingsPanel
// component can pick up the same hook without a refactor.
//
// Why localStorage and not the substrate: the toggle is operator-
// preference, not substrate state. The substrate ENFORCES the gate
// via ``policy_tag`` regardless of what the operator clicked
// (master-spec §9.0). The localStorage value is a UI-side hint that
// the surface passes through to ``fetchCrossDocLinks``.
//
// Master-spec dependency reminder: when ``includePublicGraph`` is
// true and the receiving doc has ``content_class='restricted_pending_
// opt_in'``, the substrate STILL hides it because the cross-doc
// caller hits the 'operator_only' policy tag — the public-graph
// toggle does not bypass §9.0. Sprint 19 §13.9 attribution flows are
// what unlocks the full public-graph experience; until then the
// toggle is a forward-compatible no-op for restricted content.

import { create } from "zustand";

const STORAGE_KEY = "antiek.settings.crossDoc.includePublicGraph";

interface UserSettingsState {
  includePublicGraphInCrossDoc: boolean;
  setIncludePublicGraphInCrossDoc: (v: boolean) => void;
}

function readInitial(): boolean {
  // SSR-safe: returns default when window is absent. The reading
  // surface only runs in browser today, but the guard costs nothing.
  if (typeof window === "undefined") return false;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw === "true";
  } catch {
    // Private-window or quota-exceeded — fall through to default.
    return false;
  }
}

function persist(v: boolean): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, v ? "true" : "false");
  } catch {
    // Best-effort persistence. The next session will start at the
    // default; that's a known trade-off of localStorage discipline.
  }
}

export const useUserSettings = create<UserSettingsState>((set) => ({
  // Default per SPR-07 M7: PUBLIC GRAPH IS OFF. The §13.9 attribution
  // flows aren't live yet; offering public-graph results would create
  // a UX contract we cannot yet honor (the cite-jump target may not
  // be readable in full). Flipping default to true is a Sprint 19
  // gate.
  includePublicGraphInCrossDoc: readInitial(),
  setIncludePublicGraphInCrossDoc: (v: boolean) => {
    persist(v);
    set({ includePublicGraphInCrossDoc: v });
  },
}));

// Test-only helper: reset to the disk-backed initial. Not exported in
// the package barrel — direct importers (Vitest) reach in via path.
export function _resetUserSettingsForTest(): void {
  if (typeof window !== "undefined") {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }
  useUserSettings.setState({ includePublicGraphInCrossDoc: false });
}
