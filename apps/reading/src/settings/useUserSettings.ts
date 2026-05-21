// React hook for the SPR-04 user-settings store.
//
// Thin wrapper around userSettings.ts so components can subscribe to
// changes without each one wiring its own subscribe/unsubscribe. The
// hook is intentionally tiny — keeping the persistence + new-vs-existing
// migration logic in the plain-TS module makes it testable without
// React Testing Library.

import { useCallback, useEffect, useState } from "react";

import {
  getUserSettings,
  subscribeUserSettings,
  updateUserSettings,
  type UserSettings,
} from "./userSettings";

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
    // Synchronize once on mount in case the store changed before the
    // effect attached (e.g. another hook instance updated it during
    // the same tick).
    setSettings(getUserSettings());
    return unsubscribe;
  }, []);

  const update = useCallback(
    (patch: Partial<UserSettings>): UserSettings => updateUserSettings(patch),
    [],
  );

  return [settings, update];
}
