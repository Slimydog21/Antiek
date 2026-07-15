/**
 * Decision-tree tab — model pick + budget bar + prompt projection.
 *
 * Operator vision: choose a model driver per prompt; see usage vs budget;
 * project how the proposed prompt would affect the limit. Authority is
 * advisory — the operator always consents.
 *
 * Demo mode uses local fixture bench/usage when live ledger is unavailable
 * (merge wall). Replace fixtures via props without rewriting pure compose.
 */

import { useMemo, useState } from "react";

import { localHeuristicRecommend } from "../../../settings/notdiamond/shadowRouter";
import {
  composeSelectionDecision,
  type ModelConfig,
  type BenchScore,
  type BudgetUsage,
} from "./decision";
import type { NotDiamondMode } from "./notDiamondPolicy";

const DEMO_MODELS: ModelConfig[] = [
  {
    modelId: "grok-composer-2.5",
    provider: "xai",
    apiKeyId: "key-xai",
    label: "Grok Composer 2.5",
  },
  {
    modelId: "gpt-5.5",
    provider: "openai",
    apiKeyId: "key-openai",
    label: "GPT 5.5",
  },
  {
    modelId: "claude-opus-4.8",
    provider: "anthropic",
    apiKeyId: "key-anthropic",
    label: "Claude Opus 4.8",
  },
  {
    modelId: "mimo-v2.5-pro",
    provider: "mimo",
    apiKeyId: "key-mimo",
    label: "MiMo V2.5 Pro",
  },
];

const DEMO_SCORES: BenchScore[] = [
  { modelId: "grok-composer-2.5", taskId: "research_synth", score: 0.88 },
  { modelId: "gpt-5.5", taskId: "research_synth", score: 0.91 },
  { modelId: "claude-opus-4.8", taskId: "research_synth", score: 0.93 },
  { modelId: "mimo-v2.5-pro", taskId: "research_synth", score: 0.84 },
  { modelId: "grok-composer-2.5", taskId: "reading_highlight", score: 0.9 },
  { modelId: "gpt-5.5", taskId: "reading_highlight", score: 0.86 },
  { modelId: "claude-opus-4.8", taskId: "reading_highlight", score: 0.89 },
  { modelId: "mimo-v2.5-pro", taskId: "reading_highlight", score: 0.87 },
];

const DEMO_USAGE: Record<string, BudgetUsage> = {
  "key-xai": { apiKeyId: "key-xai", usedCents: 420, limitCents: 2000 },
  "key-openai": { apiKeyId: "key-openai", usedCents: 1800, limitCents: 2000 },
  "key-anthropic": {
    apiKeyId: "key-anthropic",
    usedCents: 900,
    limitCents: 5000,
  },
  "key-mimo": { apiKeyId: "key-mimo", usedCents: 50, limitCents: 0 },
};

const TASKS = [
  { id: "research_synth", label: "Deep research synthesis" },
  { id: "reading_highlight", label: "Reading highlight chase" },
] as const;

/** Rough demo rate card (cents per 1k tokens) — replace with live rate card. */
const CENTS_PER_1K: Record<string, number> = {
  "grok-composer-2.5": 0.4,
  "gpt-5.5": 1.2,
  "claude-opus-4.8": 1.5,
  "mimo-v2.5-pro": 0.3,
};

export type ModelDecisionTreeTabProps = {
  models?: ModelConfig[];
  benchScores?: BenchScore[];
  usageByKey?: Record<string, BudgetUsage>;
  /**
   * NotDiamond UI mode (policy: never live authority).
   * disabled = hide chip; shadow = log-only attribute, no Accept;
   * advisory = show recommendation + Accept (operator still consents).
   */
  notDiamondMode?: NotDiamondMode;
};

export function ModelDecisionTreeTab({
  models = DEMO_MODELS,
  benchScores = DEMO_SCORES,
  usageByKey = DEMO_USAGE,
  notDiamondMode = "disabled",
}: ModelDecisionTreeTabProps) {
  const [taskId, setTaskId] = useState<string>(TASKS[0].id);
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [estimatedTokens, setEstimatedTokens] = useState(8_000);

  const selected = models.find((m) => m.modelId === selectedModelId) ?? null;
  const usage = selected ? usageByKey[selected.apiKeyId] ?? null : null;

  // Local heuristic stand-in for ND recommend until transport is opted in.
  // Never auto-applies — Accept only in advisory mode pins the selection.
  const shadowSuggestion = useMemo(() => {
    if (notDiamondMode === "disabled") return null;
    const candidates = models.map((m) => ({
      id: m.modelId,
      provider: m.provider,
    }));
    const rec = localHeuristicRecommend(candidates, taskId);
    if (!rec) return null;
    const cfg = models.find((m) => m.modelId === rec.id) ?? null;
    return cfg
      ? { modelId: cfg.modelId, label: cfg.label ?? cfg.modelId, provider: cfg.provider }
      : null;
  }, [models, taskId, notDiamondMode]);

  const decision = useMemo(
    () =>
      composeSelectionDecision({
        taskId,
        models,
        benchScores,
        usage,
        projectionRequest:
          selected && usage
            ? {
                apiKeyId: selected.apiKeyId,
                modelId: selected.modelId,
                estimatedTokens,
                centsPer1kTokens: CENTS_PER_1K[selected.modelId] ?? 1,
              }
            : null,
      }),
    [taskId, models, benchScores, usage, selected, estimatedTokens],
  );

  const bar = decision.budgetBar;
  const fillPct =
    bar?.ratio == null
      ? null
      : Math.min(100, Math.max(0, bar.ratio * 100));
  const projFillPct =
    decision.projection?.postProjectionRatio == null
      ? null
      : Math.min(
          100,
          Math.max(0, decision.projection.postProjectionRatio * 100),
        );

  return (
    <section
      data-testid="model-decision-tree-tab"
      className="space-y-4"
      aria-label="Model decision tree"
    >
      <header className="space-y-1">
        <h2 className="text-lg font-serif text-ink dark:text-bright">
          Model decision tree
        </h2>
        <p className="text-sm text-ink-soft dark:text-starlight font-serif italic">
          Advisory rankings from Antiek-bench scores, budget bar per API key,
          and prompt cost projection. Operator always consents — authority is
          never binding.
        </p>
        <div
          data-testid="model-decision-authority"
          className="font-mono text-[10px] uppercase tracking-wide text-shadow-1 dark:text-moonlight"
        >
          authority: {decision.authority}
        </div>
      </header>

      <div className="flex flex-wrap gap-3 items-end">
        <label className="flex flex-col gap-1 text-[11px] font-mono uppercase text-shadow-1 dark:text-moonlight">
          Task
          <select
            data-testid="model-decision-task"
            className="rounded border border-rule bg-ice-1 px-2 py-1 text-[13px] text-ink dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright"
            value={taskId}
            onChange={(e) => setTaskId(e.target.value)}
          >
            {TASKS.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[11px] font-mono uppercase text-shadow-1 dark:text-moonlight">
          Est. tokens
          <input
            data-testid="model-decision-tokens"
            type="number"
            min={0}
            step={500}
            value={estimatedTokens}
            onChange={(e) =>
              setEstimatedTokens(Math.max(0, Number(e.target.value) || 0))
            }
            className="w-28 rounded border border-rule bg-ice-1 px-2 py-1 text-[13px] text-ink dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright"
          />
        </label>
      </div>

      {shadowSuggestion ? (
        <div
          data-testid="model-decision-shadow-suggestion"
          data-shadow-model={shadowSuggestion.modelId}
          data-nd-mode={notDiamondMode}
          className="flex flex-wrap items-center gap-2 rounded border border-sun/40 bg-sun/10 px-3 py-2"
        >
          <span className="font-mono text-[10px] uppercase tracking-wide text-shadow-1 dark:text-moonlight">
            {notDiamondMode === "shadow" ? "Shadow log" : "Advisory suggest"}
          </span>
          <span className="min-w-0 flex-1 text-[13px] text-ink dark:text-bright">
            {shadowSuggestion.label}{" "}
            <span className="font-mono text-[10px] text-shadow-1 dark:text-moonlight">
              ({shadowSuggestion.provider})
            </span>
          </span>
          {notDiamondMode === "advisory" ? (
            <button
              type="button"
              data-testid="model-decision-shadow-accept"
              className="rounded bg-sun px-2 py-1 font-mono text-[11px] uppercase text-ink"
              onClick={() => setSelectedModelId(shadowSuggestion.modelId)}
            >
              Accept
            </button>
          ) : null}
        </div>
      ) : null}

      <details open className="rounded border border-rule dark:border-charcoal-1">
        <summary className="cursor-pointer select-none px-3 py-2 font-mono text-[11px] uppercase tracking-wide text-ink dark:text-bright">
          Ranked models (bench → task)
        </summary>
        <ul className="divide-y divide-rule/60 dark:divide-charcoal-1" data-testid="model-decision-rankings">
          {decision.recommendation.map((r, i) => {
            const isSelected = selectedModelId === r.modelId;
            return (
              <li key={r.modelId}>
                <button
                  type="button"
                  data-testid={`model-decision-pick-${r.modelId}`}
                  onClick={() => setSelectedModelId(r.modelId)}
                  className={
                    "flex w-full items-center gap-3 px-3 py-2 text-left text-[13px] " +
                    (isSelected
                      ? "bg-sun/15"
                      : "hover:bg-ice-2/80 dark:hover:bg-charcoal-1/60")
                  }
                >
                  <span className="w-6 font-mono text-[11px] text-shadow-1 dark:text-moonlight">
                    #{i + 1}
                  </span>
                  <span className="min-w-0 flex-1 truncate font-medium text-ink dark:text-bright">
                    {r.label}
                  </span>
                  <span className="font-mono text-[11px] text-shadow-1 dark:text-moonlight">
                    {(r.score * 100).toFixed(0)}%
                  </span>
                  <span className="font-mono text-[10px] uppercase text-shadow-1 dark:text-moonlight">
                    {r.provider}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </details>

      {selected ? (
        <div
          data-testid="model-decision-budget"
          className="space-y-2 rounded border border-rule p-3 dark:border-charcoal-1"
        >
          <div className="font-mono text-[11px] uppercase tracking-wide text-shadow-1 dark:text-moonlight">
            Budget · key {selected.apiKeyId}
          </div>
          {bar && fillPct != null ? (
            <>
              <div className="relative h-3 overflow-hidden rounded-full bg-ice-2 dark:bg-charcoal-1">
                <div
                  data-testid="model-decision-budget-fill"
                  className="absolute inset-y-0 left-0 bg-sun/70"
                  style={{ width: `${fillPct}%` }}
                />
                {projFillPct != null && projFillPct > fillPct ? (
                  <div
                    data-testid="model-decision-projection-fill"
                    className="absolute inset-y-0 left-0 bg-emperor/40"
                    style={{ width: `${projFillPct}%` }}
                  />
                ) : null}
              </div>
              <div className="font-mono text-[11px] text-ink dark:text-bright">
                {(bar.usedCents / 100).toFixed(2)} /{" "}
                {(bar.limitCents / 100).toFixed(2)} USD used
                {decision.projection
                  ? ` · +$${(decision.projection.projectedCents / 100).toFixed(2)} projected`
                  : ""}
              </div>
            </>
          ) : (
            <div
              data-testid="model-decision-budget-unconfigured"
              className="font-mono text-[11px] text-shadow-1 dark:text-moonlight"
            >
              Budget limit unconfigured for this key (ratio deferred).
            </div>
          )}

          {decision.projection?.wouldExceed ? (
            <div
              data-testid="model-decision-would-exceed"
              role="alert"
              className="rounded border border-emperor/50 bg-emperor/10 px-2 py-1.5 text-[12px] text-ink dark:text-bright"
            >
              This prompt is projected to exceed your budget limit. Advisory
              only — you may still proceed.
            </div>
          ) : null}

          <div
            data-testid="model-decision-selected"
            className="font-mono text-[11px] text-shadow-1 dark:text-moonlight"
          >
            Selected driver: {selected.label ?? selected.modelId} (operator
            consent required at dispatch)
          </div>
        </div>
      ) : (
        <div className="font-mono text-[11px] text-shadow-1 dark:text-moonlight">
          Select a model to inspect budget bar and prompt projection.
        </div>
      )}
    </section>
  );
}

export default ModelDecisionTreeTab;
