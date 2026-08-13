/**
 * Tier overrides — OYM P1 §5 (visible tiers, WRITE half).
 *
 * The read half (P0) renders chunk_tier_overrides inside the Explain
 * provenance chains; this client is the user-settable half:
 *
 *   GET  /settings/tier-overrides?chunk_id=... — one chunk's append-only
 *        override history (newest first) + the tier it currently carries
 *   POST /settings/tier-overrides               — append one override row
 *        {chunk_id, override_tier, reason}      (set_by/reason/set_at come
 *        back stamped by the server; the table is an audit trail — newer
 *        overrides supersede, nothing is ever deleted)
 *
 * The row shape reuses `TierOverride` from ownYourMind.ts (the single
 * typed seam the Explain panel already reads); the response envelope
 * mirrors interfaces/research/api/settings_tiers.py.
 */

import { API_BASE, ApiError, apiFetch } from "../lib/api";

import type { TierOverride } from "./ownYourMind";

/** GET /settings/tier-overrides?chunk_id=... payload. */
export interface TierOverridesResponse {
  chunk_id: string;
  /** The tier the chunk currently carries (its source document's tier). */
  current_original_tier: number;
  /** Override history, newest first. */
  overrides: TierOverride[];
}

export async function getTierOverrides(
  chunkId: string,
): Promise<TierOverridesResponse> {
  const resp = await apiFetch(
    `${API_BASE}/settings/tier-overrides?chunk_id=${encodeURIComponent(chunkId)}`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /settings/tier-overrides failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json() as Promise<TierOverridesResponse>;
}

export async function createTierOverride(
  chunkId: string,
  overrideTier: number,
  reason: string,
): Promise<TierOverride> {
  const resp = await apiFetch(`${API_BASE}/settings/tier-overrides`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chunk_id: chunkId,
      override_tier: overrideTier,
      reason,
    }),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /settings/tier-overrides failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json() as Promise<TierOverride>;
}
