/**
 * researchTier — map Settings depth-tier presets ↔ research entry tiers.
 *
 * Residual (gt): Settings `flash|pro|wrestle` is the operator's durable depth
 * preference; StartResearch / Midnight Oil / ChatInput use closed
 * ResearchTier `fast|deep|wrestle`. This pure map keeps them aligned without
 * inventing providers.
 */

import type { ResearchTier } from "./api";

/** Settings depth-tier ids from GET /settings/depth-tier. */
export type DepthTierId = "flash" | "pro" | "wrestle" | string;

/**
 * Map Settings active_depth_tier → ResearchTier for launch surfaces.
 * Returns null when unknown / unset so callers keep their default.
 */
export function mapDepthTierToResearchTier(
  depthTier: DepthTierId | null | undefined,
): ResearchTier | null {
  const d = String(depthTier || "")
    .trim()
    .toLowerCase();
  if (!d) return null;
  if (d === "flash" || d === "fast") return "fast";
  if (d === "pro" || d === "deep") return "deep";
  if (d === "wrestle") return "wrestle";
  return null;
}

/** Inverse for display / Settings install hints (projection only). */
export function mapResearchTierToDepthTier(
  researchTier: ResearchTier | null | undefined,
): "flash" | "pro" | "wrestle" | null {
  if (researchTier === "fast") return "flash";
  if (researchTier === "deep") return "pro";
  if (researchTier === "wrestle") return "wrestle";
  return null;
}
