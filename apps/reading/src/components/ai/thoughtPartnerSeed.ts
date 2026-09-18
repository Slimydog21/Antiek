/**
 * Shared thought-partner seed event (Surface E + AISidecar + future hosts).
 * Cite: master-spec §4.5 — parked question / selection seeds the partner.
 * SERVABLE reading mount: composeThoughtPartnerSystemContext (#3135 dual structure).
 */
import { formatReadingFocusSystemContext } from "../../lib/readingFocus";
import { workspaceContextPrompt } from "./aiActions";

export const THOUGHT_PARTNER_SEED_EVENT = "antiek:thought-partner:seed";

export interface ThoughtPartnerSeedDetail {
  prompt?: string;
  system_context?: string;
  source_label?: string;
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
