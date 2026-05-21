// React hook for the SPR-04 reading-mode settings store.
//
// Renamed import target from `./userSettings` to `./readingModeSettings`
// during integration: SPR-06 added a different `userSettings.ts` at the
// same path with a non-overlapping schema. See the header of
// `readingModeSettings.ts` for the full rationale.
//
// Thin wrapper around readingModeSettings.ts so components can subscribe
// to changes without each one wiring its own subscribe/unsubscribe.

import { useCallback, useEffect, useState } from "react";

import {
  getUserSettings,
  subscribeUserSettings,
  updateUserSettings,
  type UserSettings,
} from "./readingModeSettings";

/**
 * Returns the current settings and a setter that updates the global
 * store. The setter merges (does not replace) so callers only need to
 * pass the fields they care about.
 */
export function useUserSettings(): [
  UserSettings,
  (patch: Partial<UserSettings>) => UserSettings,
] {
  const [settings, setSettings] = useState<UserSettings>(() => getUserSettings());

  useEffect(() => {
    const unsubscribe = subscribeUserSettings((next) => {
      setSettings(next);
    });
    setSettings(getUserSettings());
    return unsubscribe;
  }, []);

  const update = useCallback(
    (patch: Partial<UserSettings>): UserSettings => updateUserSettings(patch),
    [],
  );

  return [settings, update];
}
