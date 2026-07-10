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

/** Antiek-bench recursive suite rewrite task classes. */
export type AntiekBenchTaskClass =
  | "distill"
  | "synthesize"
  | "wrestle"
  | "book_qa";

/**
 * Residual (gw): map ResearchTier → Antiek-bench task_class (parity with
 * substrate.antiek_bench.usage_bridge.research_tier_to_task_class).
 * Returns null when unset so callers keep engagement heuristics.
 */
export function mapResearchTierToBenchTaskClass(
  researchTier: ResearchTier | string | null | undefined,
): AntiekBenchTaskClass | null {
  const t = String(researchTier || "")
    .trim()
    .toLowerCase();
  if (!t) return null;
  if (t === "wrestle") return "wrestle";
  if (t === "fast" || t === "flash") return "distill";
  if (t === "deep" || t === "pro") return "synthesize";
  return null;
}

/**
 * Residual (ju): progress poll cadence by research_tier intensity.
 * One closed map for DeepResearchSessionHost + Midnight Oil deposit
 * (fast 2s · deep 4s · wrestle 8s multi-minute competitive posture).
 * Unknown/unset → deep default (4000ms).
 */
export const RESEARCH_TIER_PROGRESS_POLL_MS = {
  fast: 2000,
  deep: 4000,
  wrestle: 8000,
} as const;

export function mapResearchTierToProgressPollMs(
  researchTier: ResearchTier | string | null | undefined,
): number {
  const t = String(researchTier || "")
    .trim()
    .toLowerCase();
  if (t === "fast" || t === "flash") return RESEARCH_TIER_PROGRESS_POLL_MS.fast;
  if (t === "wrestle") return RESEARCH_TIER_PROGRESS_POLL_MS.wrestle;
  return RESEARCH_TIER_PROGRESS_POLL_MS.deep;
}

/**
 * Residual (jv): Midnight Oil ceiling intensity multipliers.
 * Mirrors substrate/midnight_oil/ceiling.py TIER_MULTIPLIER
 * (fast 0.5 · deep 1.0 · wrestle 2.0). Display/audit only on client —
 * server still owns the recommended ceiling math.
 */
export const RESEARCH_TIER_CEILING_MULTIPLIER = {
  fast: 0.5,
  deep: 1.0,
  wrestle: 2.0,
} as const;

/**
 * Residual (ada): Midnight Oil ceiling formula constants (parity substrate
 * midnight_oil.ceiling — TOKENS_PER_MINUTE / SAFETY_FACTOR / DEFAULT_FANOUT).
 * Machine-readable on MO formula chrome; never invent live rates here.
 */
export const MOIL_CEILING_TOKENS_PER_MINUTE = 4000;
export const MOIL_CEILING_SAFETY_FACTOR = 1.25;
export const MOIL_CEILING_DEFAULT_FANOUT_DEPTH = 3;

export function mapResearchTierToCeilingMultiplier(
  researchTier: ResearchTier | string | null | undefined,
): number {
  const t = String(researchTier || "")
    .trim()
    .toLowerCase();
  if (t === "fast" || t === "flash") {
    return RESEARCH_TIER_CEILING_MULTIPLIER.fast;
  }
  if (t === "wrestle") return RESEARCH_TIER_CEILING_MULTIPLIER.wrestle;
  return RESEARCH_TIER_CEILING_MULTIPLIER.deep;
}

/** Operator-facing label for MO tier factor chrome. */
export function formatResearchTierCeilingFactor(
  researchTier: ResearchTier | string | null | undefined,
): string {
  const t = String(researchTier || "")
    .trim()
    .toLowerCase();
  const mult = mapResearchTierToCeilingMultiplier(t);
  const name =
    t === "fast" || t === "flash"
      ? "fast"
      : t === "wrestle"
        ? "wrestle"
        : "deep";
  return `${mult.toFixed(1)}× (${name})`;
}

/**
 * Residual (ng): competitive duration recommendation for Midnight Oil
 * autonomous runs (parity ResearchProgressPanel mw bands).
 * Honest estimate midpoints — not a live ETA; operator can override.
 *   fast 1–3m → 3 · deep 3–10m → 10 · wrestle 10–30+m → 30
 */
export const RESEARCH_TIER_RECOMMENDED_DURATION_MINUTES = {
  fast: 3,
  deep: 10,
  wrestle: 30,
} as const;

export function mapResearchTierToRecommendedDurationMinutes(
  researchTier: ResearchTier | string | null | undefined,
): number {
  const t = String(researchTier || "")
    .trim()
    .toLowerCase();
  if (t === "fast" || t === "flash") {
    return RESEARCH_TIER_RECOMMENDED_DURATION_MINUTES.fast;
  }
  if (t === "wrestle") {
    return RESEARCH_TIER_RECOMMENDED_DURATION_MINUTES.wrestle;
  }
  return RESEARCH_TIER_RECOMMENDED_DURATION_MINUTES.deep;
}

/** Competitive band label for MO duration chrome (offline-honest). */
export function formatResearchTierDurationBand(
  researchTier: ResearchTier | string | null | undefined,
): string {
  const t = String(researchTier || "")
    .trim()
    .toLowerCase();
  if (t === "fast" || t === "flash") return "1–3";
  if (t === "wrestle") return "10–30+";
  return "3–10";
}
