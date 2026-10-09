/**
 * Shared thought-partner seed event (Surface E + AISidecar + future hosts).
 * Cite: master-spec §4.5 — parked question / selection seeds the partner.
 * SERVABLE reading mount: composeThoughtPartnerSystemContext (issue 3135 dual structure).
 */
import { formatReadingFocusSystemContext } from "../../lib/readingFocus";
import { workspaceContextPrompt } from "./aiActions";

export const THOUGHT_PARTNER_SEED_EVENT = "antiek:thought-partner:seed";

export interface ThoughtPartnerSeedDetail {
  prompt?: string;
  system_context?: string;
  source_label?: string;
  /** SPR-03 Task 3: a driver choice made elsewhere (the CommandPalette's
   *  picker) for the sidecar's thought partner. `row_id` is the registered
   *  key's row id ("" = house route); `model_id` names a variant under it. */
  owner_model?: { row_id: string; model_id?: string };
}

/**
 * Base context (picker override or workspace) + current-book SERVABLE page.
 * Manual @-compose still wins as the base; reading page is always appended
 * when the BookReader has published a focus (gated ⇒ withheld stub only).
 */
export function composeThoughtPartnerSystemContext(
  composedFromPicker?: string | null,
): string {
  const base = (composedFromPicker || "").trim()
    ? (composedFromPicker || "").trim()
    : workspaceContextPrompt();
  const reading = formatReadingFocusSystemContext();
  if (!reading) return base;
  return `${base}\n\n${reading}`;
}

/**
 * FFX-KPA SPR-03 M5 — seed a pane that may not be mounted yet. The AISidecar
 * is a lazy panel: opening it and dispatching in the same tick would fire the
 * event before its listener exists. So the seed is parked here as well as
 * broadcast; a listener that is already mounted takes it on the event, and a
 * sidecar that mounts afterwards takes it on mount. A parked seed expires so
 * an old draft never lands in a pane opened much later.
 */
const PENDING_SEED_TTL_MS = 10_000;
let pendingSeed: { detail: ThoughtPartnerSeedDetail; at: number } | null = null;

export function seedThoughtPartner(detail: ThoughtPartnerSeedDetail): void {
  pendingSeed = { detail, at: Date.now() };
  window.dispatchEvent(new CustomEvent(THOUGHT_PARTNER_SEED_EVENT, { detail }));
}

/** Take (and clear) a parked seed that is still fresh. */
export function takePendingThoughtPartnerSeed(now = Date.now()): ThoughtPartnerSeedDetail | null {
  const seed = pendingSeed;
  pendingSeed = null;
  if (!seed || now - seed.at > PENDING_SEED_TTL_MS) return null;
  return seed.detail;
}
