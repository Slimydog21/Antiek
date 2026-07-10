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
 * Residual (ady): offline default combined rates (input+output USD/1M)
 * mirroring substrate/midnight_oil/ceiling.py DEFAULT_PRICING.
 * Preview only — never invent live provider rates.
 */
export const MOIL_DEFAULT_MODEL_COMBINED_USD_PER_1M: Record<string, number> = {
  default: 4.0, // 1.0 + 3.0
  "glm-5.2": 2.0, // 0.5 + 1.5
  "gpt-5.5": 20.0, // 5.0 + 15.0
  "composer-2.5": 8.0, // 2.0 + 6.0
  "mimo-v2.5": 3.2, // 0.8 + 2.4
};

/** Resolve offline combined rate for MO ceiling preview (ady). */
export function resolveMoilPreviewCombinedUsdPer1m(
  modelId?: string | null,
): { combined: number; pricing_source: string } {
  const key = String(modelId || "default").trim() || "default";
  if (key in MOIL_DEFAULT_MODEL_COMBINED_USD_PER_1M) {
    return {
      combined: MOIL_DEFAULT_MODEL_COMBINED_USD_PER_1M[key]!,
      pricing_source: `offline-table:${key}`,
    };
  }
  return {
    combined: MOIL_DEFAULT_MODEL_COMBINED_USD_PER_1M.default,
    pricing_source: "offline-table:default",
  };
}

/**
 * Residual (adx/ady): client preview of Midnight Oil recommended price ceiling.
 * Mirrors substrate/midnight_oil/ceiling.py recommend_price_ceiling with
 * offline model rate table when known; else default 1+3 USD/1M.
 * Preview only — create job remains authoritative server recommendation.
 */
export function estimateMoilRecommendedCeilingUsd(opts: {
  durationMinutes: number;
  fanoutDepth?: number;
  researchTier?: ResearchTier | string | null;
  /** Residual (ady): model id for offline rate table lookup. */
  modelId?: string | null;
  /** Combined input+output USD per 1M tokens; overrides model table when set. */
  combinedUsdPer1m?: number;
}): number | null {
  const duration = Math.floor(Number(opts.durationMinutes));
  if (!Number.isFinite(duration) || duration <= 0) return null;
  const fanoutRaw = Number(opts.fanoutDepth);
  const fanout =
    Number.isFinite(fanoutRaw) && fanoutRaw > 0
      ? Math.floor(fanoutRaw)
      : MOIL_CEILING_DEFAULT_FANOUT_DEPTH;
  let combined: number;
  if (
    typeof opts.combinedUsdPer1m === "number" &&
    Number.isFinite(opts.combinedUsdPer1m) &&
    opts.combinedUsdPer1m > 0
  ) {
    combined = opts.combinedUsdPer1m;
  } else {
    combined = resolveMoilPreviewCombinedUsdPer1m(opts.modelId).combined;
  }
  const mult = mapResearchTierToCeilingMultiplier(opts.researchTier);
  const raw =
    duration *
    MOIL_CEILING_TOKENS_PER_MINUTE *
    (combined / 1_000_000) *
    fanout *
    MOIL_CEILING_SAFETY_FACTOR *
    mult;
  return Math.round(raw * 100) / 100;
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
