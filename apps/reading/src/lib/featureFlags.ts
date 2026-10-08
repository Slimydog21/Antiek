/**
 * featureFlags.ts — the smallest honest flag seam. A flag is ON when
 * localStorage `antiek.flag.<name>` is "on", OFF when "off", and otherwise
 * falls back to the caller's default (dev builds default ON so the operator
 * sees the new surface; prod defaults OFF until the owning sprint flips it).
 *
 * Reads are wrapped: private windows and cleared site data throw or return
 * null, and a flag read must never take the page down. No PostHog flag
 * evaluation here — when an operator-created PostHog flag exists, the
 * owning sprint wires it through this same function so callers never change.
 */
export type FeatureFlagName = "switcher.places" | "pane.flow";

const DEV_DEFAULTS: Record<FeatureFlagName, boolean> = {
  // SPR-02 (specs/antiek-keyboard-panes-agents-20261007): places sections
  // in the Switcher + the rail strip. Flipped to prod-ON in SPR-05.
  "switcher.places": true,
  // SPR-01 M1 (pane-flow packet landing): horizontal/tiled pane arrangement,
  // the S05 ctrl+alt+l migration and the pane.reorder rows. OFF everywhere —
  // including dev — until SPR-05 flips it after the keyboard journeys pass.
  "pane.flow": false,
};

export function featureFlagKey(name: FeatureFlagName): string {
  return `antiek.flag.${name}`;
}

export function isFeatureOn(name: FeatureFlagName): boolean {
  try {
    const v = window.localStorage.getItem(featureFlagKey(name));
    if (v === "on") return true;
    if (v === "off") return false;
  } catch {
    // storage unavailable — fall through to the default
  }
  // Vitest runs with DEV=true and MODE="test": tests see the flag OFF unless
  // they set it, so every pre-existing test is a flag-off parity check.
  return import.meta.env.DEV && import.meta.env.MODE !== "test" ? DEV_DEFAULTS[name] : false;
}

export function setFeatureFlag(name: FeatureFlagName, on: boolean | null): void {
  try {
    if (on === null) window.localStorage.removeItem(featureFlagKey(name));
    else window.localStorage.setItem(featureFlagKey(name), on ? "on" : "off");
  } catch {
    // storage unavailable — a flag write is a convenience, never a failure
  }
}
