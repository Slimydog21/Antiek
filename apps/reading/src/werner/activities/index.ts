/**
 * The station-activities surface.
 *
 * Importing this module registers the built-in activities as a side effect
 * (`./rest` self-registers as the default), so any consumer that reads
 * the registry through here — the mascot, the shell, tests — sees a seeded
 * catalog. Keep the `./rest` import FIRST so the default is registered
 * before the registry accessors are used.
 *
 * WHY THE BARE `import "./rest"` SURVIVES A PROD BUILD (do not break this):
 * it is a side-effect-only import, which bundlers (Vite/Rollup) preserve UNLESS
 * the package is marked `"sideEffects": false`. `apps/reading/package.json` has
 * NO such field, so the registration is not tree-shaken away. If a future change
 * adds `"sideEffects": false` for bundle-size, this import becomes prunable and
 * `getDefaultActivity()` would throw in prod while unit tests (which import the
 * module directly) stay green — so list `src/werner/activities/*` under an
 * explicit `sideEffects` allowlist at the same time.
 */
import "./rest";
import "./researchLens";
import "./writingNib";
import "./speakingResonance";

export {
  registerActivity,
  getActivity,
  listActivities,
  getDefaultActivity,
} from "./registry";
export { restActivity } from "./rest";
export { researchLensActivity } from "./researchLens";
export { writingNibActivity } from "./writingNib";
export { speakingResonanceActivity } from "./speakingResonance";
export { activityIdForPathname, getActivityForPathname } from "./selection";
export type {
  ActivityId,
  ActivityUnlock,
  CursorInstrument,
  CursorInstrumentProps,
  InstrumentSeamField,
  StationActivity,
} from "./types";
