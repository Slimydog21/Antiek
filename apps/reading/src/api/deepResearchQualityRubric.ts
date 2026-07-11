/**
 * Deep research quality rubric (pure client).
 *
 * Operator vision: highest-quality deep research product in the world.
 * This pure layer scores research outputs against hard-to-vary dimensions
 * using only caller-supplied metrics — never invents quality from free text
 * and never calls live judges.
 *
 * overall is null when no dimension is known (never invents 0 or 1).
 */

export type QualityDimensionId =
  | "citation_density"
  | "source_diversity"
  | "claim_grounding"
  | "counterargument_coverage"
  | "intellectual_honesty"
  | "recursive_questions"
  | "actionability";

export const QUALITY_DIMENSIONS: readonly QualityDimensionId[] = [
  "citation_density",
  "source_diversity",
  "claim_grounding",
  "counterargument_coverage",
  "intellectual_honesty",
  "recursive_questions",
  "actionability",
] as const;

export const DIMENSION_WEIGHTS: Readonly<Record<QualityDimensionId, number>> = {
  citation_density: 1.2,
  source_diversity: 1.1,
  claim_grounding: 1.3,
  counterargument_coverage: 1.0,
  intellectual_honesty: 1.4,
  recursive_questions: 1.0,
  actionability: 0.9,
};

export interface DimensionScore {
  dimension: QualityDimensionId;
  /** 0..1 inclusive when known; null = unknown (never invent). */
  score: number | null;
  note?: string;
}

export interface DeepResearchQualityInput {
  research_id: string;
  /** Caller-supplied dimension scores only. */
  dimensions: DimensionScore[];
  /**
   * When true, overall requires all seven dimensions known.
   * When false (default), overall averages known dimensions only.
   */
  require_all_dimensions?: boolean;
}

export interface DimensionResult {
  dimension: QualityDimensionId;
  score: number | null;
  weight: number;
  known: boolean;
  note: string | null;
}

export interface DeepResearchQualityReport {
  research_id: string;
  dimensions: DimensionResult[];
  /** Weighted mean of known scores; null if none known or require_all fails. */
  overall: number | null;
  known_count: number;
  missing: QualityDimensionId[];
  /** Always false — pure rubric does not write product quality ledgers. */
  persisted: false;
  notes: string[];
  authority: "deep_research_quality_rubric_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function finiteUnitInterval(value: unknown, name: string): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${name} must be finite number or null`);
  }
  if (value < 0 || value > 1) {
    throw new Error(`${name} must be in [0, 1]`);
  }
  return value;
}

/**
 * Score a deep research artifact from caller-supplied dimension metrics.
 * Never invents scores from research text or live judges.
 */
export function evaluateDeepResearchQuality(
  input: DeepResearchQualityInput,
): DeepResearchQualityReport {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  const research_id = requireNonEmpty(input.research_id, "research_id");
  if (!Array.isArray(input.dimensions)) {
    throw new Error("dimensions must be an array");
  }
  const requireAll =
    input.require_all_dimensions === undefined
      ? false
      : input.require_all_dimensions;
  if (typeof requireAll !== "boolean") {
    throw new Error("require_all_dimensions must be an explicit boolean when set");
  }

  const notes: string[] = [
    "persisted=false — advisory rubric only (no quality ledger write)",
    "scores are caller-supplied only (no invent from free text / live judge)",
  ];

  const byDim = new Map<QualityDimensionId, DimensionScore>();
  for (let i = 0; i < input.dimensions.length; i++) {
    const d = input.dimensions[i];
    if (!d || typeof d !== "object") {
      throw new Error(`dimensions[${i}] must be an object`);
    }
    if (!QUALITY_DIMENSIONS.includes(d.dimension)) {
      throw new Error(
        `dimensions[${i}].dimension must be one of ${QUALITY_DIMENSIONS.join("|")}`,
      );
    }
    if (byDim.has(d.dimension)) {
      throw new Error(`duplicate dimension ${d.dimension}`);
    }
    const score = finiteUnitInterval(
      d.score,
      `dimensions[${i}].score`,
    );
    if (d.note !== undefined && d.note !== null && typeof d.note !== "string") {
      throw new Error(`dimensions[${i}].note must be string when set`);
    }
    byDim.set(d.dimension, {
      dimension: d.dimension,
      score,
      note: typeof d.note === "string" ? d.note : undefined,
    });
  }

  const dimensions: DimensionResult[] = [];
  const missing: QualityDimensionId[] = [];
  let weightSum = 0;
  let weighted = 0;
  let known_count = 0;

  for (const dim of QUALITY_DIMENSIONS) {
    const weight = DIMENSION_WEIGHTS[dim];
    const supplied = byDim.get(dim);
    const score = supplied?.score ?? null;
    const known = score !== null;
    if (!known) {
      missing.push(dim);
      dimensions.push({
        dimension: dim,
        score: null,
        weight,
        known: false,
        note: supplied?.note?.trim() || "unknown — not invented",
      });
      continue;
    }
    known_count += 1;
    weightSum += weight;
    weighted += score * weight;
    dimensions.push({
      dimension: dim,
      score,
      weight,
      known: true,
      note: supplied?.note?.trim() || null,
    });
  }

  let overall: number | null = null;
  if (requireAll && missing.length > 0) {
    notes.push(
      `require_all_dimensions=true and missing=${missing.join(",")} — overall=null`,
    );
    overall = null;
  } else if (known_count === 0 || weightSum <= 0) {
    notes.push("no known dimensions — overall=null (no invent 0)");
    overall = null;
  } else {
    overall = weighted / weightSum;
    if (!Number.isFinite(overall)) {
      throw new Error("overall overflowed to non-finite");
    }
    notes.push(
      `overall from ${known_count}/${QUALITY_DIMENSIONS.length} known dimensions`,
    );
  }

  notes.push("persisted=false");

  return {
    research_id,
    dimensions,
    overall,
    known_count,
    missing,
    persisted: false,
    notes,
    authority: "deep_research_quality_rubric_advisory",
  };
}

export function formatQualitySummary(r: DeepResearchQualityReport): string {
  const o =
    r.overall === null ? "overall=null" : `overall=${r.overall.toFixed(3)}`;
  return (
    `research=${r.research_id} · ${o} · known=${r.known_count}/7 · persisted=false`
  );
}
