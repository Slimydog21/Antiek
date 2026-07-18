/**
 * Model-selection decision-tree — pure composition (reading app).
 *
 * Mirrors `.infinite/sprint-briefs/model-selection-decision-tree-integration-spec.md`.
 * Advisory only: never auto-selects, never dispatches, never mutates.
 *
 * Hard-to-vary invariants (tests pin these):
 *   - authority is always "advisory"
 *   - budget ratio is null when limit_cents === 0 (unconfigured, not 0%)
 *   - projection is null until model + token estimate exist
 *   - would_exceed warns but never removes models from the tree
 *   - recommendation order is preserved from ranked input (no re-sort)
 */

export type ModelConfig = {
  modelId: string;
  provider: string;
  apiKeyId: string;
  /** Optional display label. */
  label?: string;
};

export type BenchScore = {
  modelId: string;
  taskId: string;
  /** Score in [0, 1]. */
  score: number;
};

export type ModelRanking = {
  modelId: string;
  score: number;
  provider: string;
  apiKeyId: string;
  label: string;
};

export type BudgetUsage = {
  apiKeyId: string;
  usedCents: number;
  limitCents: number;
};

export type BudgetBar = {
  apiKeyId: string;
  usedCents: number;
  limitCents: number;
  /** used/limit, or null when limit is 0 (unconfigured). */
  ratio: number | null;
};

export type PromptProjectionRequest = {
  apiKeyId: string;
  modelId: string;
  estimatedTokens: number;
  /** Cents per 1k tokens for this model (caller-supplied rate card). */
  centsPer1kTokens: number;
};

export type PromptProjection = {
  modelId: string;
  projectedCents: number;
  postProjectionUsedCents: number;
  postProjectionRatio: number | null;
  wouldExceed: boolean;
};

export type ModelFitReport = {
  modelId: string;
  taskId: string;
  /** Was this model the best pick for the task? 1 = yes. */
  wasBest: boolean;
  score: number;
  bestScore: number;
};

export type ModelSelectionDecision = {
  taskId: string;
  recommendation: ModelRanking[];
  budgetBar: BudgetBar | null;
  projection: PromptProjection | null;
  fitFeedback: ModelFitReport | null;
  authority: "advisory";
};

export type ComposeSelectionInput = {
  taskId: string;
  models: ModelConfig[];
  benchScores: BenchScore[];
  /** Usage for the key the operator is currently budgeting against. */
  usage?: BudgetUsage | null;
  projectionRequest?: PromptProjectionRequest | null;
  fitFeedback?: ModelFitReport | null;
};

function clamp01(n: number): number {
  if (Number.isNaN(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

/**
 * Rank models for a task from bench scores. Models without a score sort last
 * with score 0. Order is deterministic: score desc, then modelId asc.
 */
export function rankModelsForTask(
  taskId: string,
  models: ModelConfig[],
  benchScores: BenchScore[],
): ModelRanking[] {
  const scoreByModel = new Map<string, number>();
  for (const s of benchScores) {
    if (s.taskId !== taskId) continue;
    scoreByModel.set(s.modelId, clamp01(s.score));
  }
  const ranked: ModelRanking[] = models.map((m) => ({
    modelId: m.modelId,
    score: scoreByModel.get(m.modelId) ?? 0,
    provider: m.provider,
    apiKeyId: m.apiKeyId,
    label: m.label ?? m.modelId,
  }));
  ranked.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return a.modelId.localeCompare(b.modelId);
  });
  return ranked;
}

export function buildBudgetBar(usage: BudgetUsage | null | undefined): BudgetBar | null {
  if (!usage) return null;
  const { apiKeyId, usedCents, limitCents } = usage;
  const ratio =
    limitCents === 0 ? null : usedCents / limitCents;
  return { apiKeyId, usedCents, limitCents, ratio };
}

export function projectPromptCost(
  usage: BudgetUsage | null | undefined,
  req: PromptProjectionRequest | null | undefined,
): PromptProjection | null {
  if (!usage || !req) return null;
  if (req.apiKeyId !== usage.apiKeyId) return null;
  if (!(req.estimatedTokens > 0) || !(req.centsPer1kTokens >= 0)) return null;

  const projectedCents =
    (req.estimatedTokens / 1000) * req.centsPer1kTokens;
  const post = usage.usedCents + projectedCents;
  const postRatio =
    usage.limitCents === 0 ? null : post / usage.limitCents;
  const wouldExceed =
    usage.limitCents > 0 && post > usage.limitCents;

  return {
    modelId: req.modelId,
    projectedCents,
    postProjectionUsedCents: post,
    postProjectionRatio: postRatio,
    wouldExceed,
  };
}

/**
 * Pure composition entry — one advisory object for the decision-tree tab.
 */
export function composeSelectionDecision(
  input: ComposeSelectionInput,
): ModelSelectionDecision {
  const recommendation = rankModelsForTask(
    input.taskId,
    input.models,
    input.benchScores,
  );
  const budgetBar = buildBudgetBar(input.usage ?? null);
  const projection = projectPromptCost(
    input.usage ?? null,
    input.projectionRequest ?? null,
  );

  return {
    taskId: input.taskId,
    recommendation,
    budgetBar,
    projection,
    fitFeedback: input.fitFeedback ?? null,
    authority: "advisory",
  };
}
