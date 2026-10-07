/**
 * flags.ts — the smallest flag seam the zen home needs (FFX-KPA SPR-03 M7).
 * main had no flag mechanism when this landed; Antiek Sweep's PR #3748 adds
 * lib/featureFlags.ts with the same semantics, and the two fold into one file
 * when both are on main.
 *
 * A flag is ON only when localStorage holds "on" under its key. Every flag
 * here ships dark: no build or mode turns it on by default. Reads never throw
 * (private windows and cleared site data refuse storage).
 */
export type FlagKey = "antiek.nav.zenhome";

export function isFlagOn(key: FlagKey): boolean {
  try {
    return window.localStorage.getItem(key) === "on";
  } catch {
    return false;
  }
}

export function setFlag(key: FlagKey, on: boolean): void {
  try {
    if (on) window.localStorage.setItem(key, "on");
    else window.localStorage.removeItem(key);
  } catch {
    // storage unavailable: a flag write is a convenience, never a failure
  }
}
