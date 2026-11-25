import type { useCompanion } from "./companionStore";

/** The lazy pane registers its actual store after creation. Entry-chunk keys
 *  stay synchronous and refuse until that store has loaded. */
export const companionHandle: { store: typeof useCompanion | null } = { store: null };
