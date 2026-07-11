/**
 * Map Settings model inventory rows into DecisionTreePanel candidates.
 *
 * Pure — no network. Callers fetch inventory via their own client (settings.ts
 * may be owned by another lane) and pass the rows here.
 */

import type { DecisionModelIn, ModelTier } from "./modelDecision";

/** Minimal inventory row shape (compatible with GET /settings/models). */
export interface InventoryModelRow {
  provider_id: string;
  ready: boolean;
  tier_bindings?: string[] | null;
  primary_model?: string | null;
  notes?: string | null;
  /** Optional USD/1k if the inventory ever surfaces it. */
  usd_per_1k_tokens?: number | null;
}

function inferTier(bindings: string[] | null | undefined): ModelTier {
  const set = new Set((bindings ?? []).map((b) => b.toLowerCase()));
  if (set.has("reasoning") || set.has("smart") || set.has("opus")) return "reasoning";
  if (set.has("flash") || set.has("fast") || set.has("mini")) return "flash";
  if (set.has("balanced") || set.has("default") || set.has("sonnet")) return "balanced";
  return "unknown";
}

/**
 * Convert inventory rows to decision-tree candidates.
 *
 * - `ready: false` → `enabled: false` (still listed so the operator sees gaps)
 * - missing primary_model → skipped (cannot rank an empty model id)
 */
export function inventoryToDecisionModels(
  rows: InventoryModelRow[] | null | undefined,
): DecisionModelIn[] {
  if (!rows || rows.length === 0) return [];
  const out: DecisionModelIn[] = [];
  for (const row of rows) {
    const modelId = (row.primary_model ?? "").trim();
    if (!modelId) continue;
    out.push({
      model_id: modelId,
      provider: row.provider_id,
      tier: inferTier(row.tier_bindings),
      usd_per_1k_tokens:
        row.usd_per_1k_tokens === undefined ? null : row.usd_per_1k_tokens,
      enabled: Boolean(row.ready),
    });
  }
  return out;
}

/** Prefer ready models; if none ready, return all (caller may still rank disabled). */
export function preferReadyModels(models: DecisionModelIn[]): DecisionModelIn[] {
  const ready = models.filter((m) => m.enabled !== false);
  return ready.length > 0 ? ready : models;
}
