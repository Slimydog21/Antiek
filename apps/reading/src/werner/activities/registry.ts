import type { ActivityId, StationActivity } from "./types";

/**
 * The station-activity registry — a tiny, framework-free catalog.
 *
 * ─── WHY A REGISTRY FOR (TODAY) ONE ACTIVITY ────────────────────────────────
 * A maintainer will find one activity here (ice-fishing) and want to inline it.
 * Do NOT — the registry earns its keep for two reasons, both of which outlive
 * the single-entry moment:
 *   1. It is where the no-move invariant of `StationActivity` (types.ts) is
 *      given a home: activities enter Werner's world ONLY as a StationActivity,
 *      so the "an activity cannot steer the penguin" guarantee the fixed-station
 *      rework fought for is enforced at the one door, not per call-site.
 *   2. SPR-03 (switching), SPR-04 (easter egg) and SPR-05 (the arcade) add
 *      their activities as REGISTRATIONS against this surface — not by editing
 *      PenguinMascot. This sprint builds the spine those three hang from.
 * See docs/htmlspec/werner-fixed-station/DESIGN.md and the Werner Station spec.
 *
 * This module is pure (no React) so it is unit-testable in isolation. It is the
 * catalog + the notion of a default; it does NOT own "which activity is active"
 * (that is SPR-03's switch state) — with one activity, active is trivially the
 * default.
 * ─────────────────────────────────────────────────────────────────────────────
 */

// Process-global mutable catalog. There is deliberately no reset export: this
// sprint only ever registers ice-fishing (idempotently), so cross-test leakage
// is a non-issue. SPR-03 (which adds a second activity + switch state) is the
// point to add a test-only reset seam — the first test that registers a THROW-
// AWAY activity/default would otherwise leak across files with no teardown.
const catalog = new Map<ActivityId, StationActivity>();
let defaultId: ActivityId | null = null;

/**
 * Register (or replace) an activity. Idempotent by `id`: re-registering the
 * same id replaces the entry, never duplicates it. Pass `{ default: true }` to
 * mark it the default activity (the last such call wins).
 */
export function registerActivity(
  activity: StationActivity,
  options: { default?: boolean } = {},
): void {
  catalog.set(activity.id, activity);
  if (options.default) defaultId = activity.id;
}

/** Look an activity up by id; undefined if it was never registered. */
export function getActivity(id: ActivityId): StationActivity | undefined {
  return catalog.get(id);
}

/** The full catalog as a frozen snapshot (insertion order). Frozen so no
 *  caller can mutate the registry through the returned array. */
export function listActivities(): readonly StationActivity[] {
  return Object.freeze([...catalog.values()]);
}

/**
 * The default activity — the one Werner runs when nothing else is switched in.
 * Throws if none was registered (a wiring bug, not a runtime condition): the
 * mascot cannot render "the active activity" if the catalog was never seeded.
 */
export function getDefaultActivity(): StationActivity {
  if (defaultId === null) {
    throw new Error("Werner station: no default activity registered");
  }
  const activity = catalog.get(defaultId);
  if (!activity) {
    throw new Error(
      `Werner station: default activity "${defaultId}" is not in the catalog`,
    );
  }
  return activity;
}
