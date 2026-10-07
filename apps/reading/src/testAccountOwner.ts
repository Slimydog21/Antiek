import { afterEach, beforeEach, expect } from "vitest";
import { accountStorageKey, setWorkspaceOwner } from "./lib/accountWorkspaceOwner";
import { tabTreeHandle } from "./workspace/tabTreeHandle";

// Isolated component/store tests have no AuthProvider. Give their caches an
// explicit unit actor; auth boundary suites override this with unknown/null.
beforeEach(() => {
  setWorkspaceOwner(expect.getState().testPath?.includes("/lib/auth.") ? null : "unit-test-owner");
  tabTreeHandle.store?.getState().resetTabTrees();
});
afterEach(() => { setWorkspaceOwner(null); });

export function unitAccountKey(key: string): string {
  const qualified = accountStorageKey(key);
  if (qualified === null) throw new Error("This cache fixture requires an explicit unit owner");
  return qualified;
}
