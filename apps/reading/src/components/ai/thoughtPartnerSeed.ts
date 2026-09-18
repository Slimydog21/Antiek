/**
 * Shared thought-partner seed event (Surface E + AISidecar + future hosts).
 * Cite: master-spec §4.5 — parked question / selection seeds the partner.
 */
export const THOUGHT_PARTNER_SEED_EVENT = "antiek:thought-partner:seed";

export interface ThoughtPartnerSeedDetail {
  prompt?: string;
  system_context?: string;
  source_label?: string;
}
