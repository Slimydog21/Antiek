/**
 * DecisionTreePanel — operator model-choice tab (advisory only).
 *
 * Consumes POST /settings/model-decision/rank (PR #783). Does not dispatch
 * models. Shows remaining budget honestly (null → "unknown", never $0-faked)
 * and would_exceed per ranked model.
 *
 * Mount from Settings/index.tsx when that file is free (currently owned by
 * the settings-budget-ui-honesty lane). This panel is self-contained.
 */

import { useMemo, useState } from "react";
import { LemonButton, LemonCard, LemonInput, LemonSelect } from "../../components/lemon";
import {
  authorityIsAdvisory,
  formatRemaining,
  formatUsd,
  formatWouldExceed,
  rankModelsForTask,
  type DecisionModelIn,
  type DecisionTreeRankResponse,
} from "../../api/modelDecision";

const TASK_OPTIONS = [
  { value: "deep_research", label: "Deep research" },
  { value: "reading", label: "Reading" },
  { value: "note_taker", label: "Note taker" },
  { value: "synthesis", label: "Synthesis" },
  { value: "write", label: "Write" },
  { value: "general", label: "General" },
];

const DEFAULT_MODELS: DecisionModelIn[] = [
  {
    model_id: "reasoning-default",
    provider: "house",
    tier: "reasoning",
    usd_per_1k_tokens: 0.015,
  },
  {
    model_id: "balanced-default",
    provider: "house",
    tier: "balanced",
    usd_per_1k_tokens: 0.005,
  },
  {
    model_id: "flash-default",
    provider: "house",
    tier: "flash",
    usd_per_1k_tokens: 0.001,
  },
];

export interface DecisionTreePanelProps {
  /** Optional preloaded inventory; defaults to three house tier placeholders. */
  models?: DecisionModelIn[];
  /** Injectable ranker for offline tests. */
  rankFn?: typeof rankModelsForTask;
  /** Initial remaining budget (null = unknown). */
  initialRemainingUsd?: number | null;
}

export default function DecisionTreePanel({
  models = DEFAULT_MODELS,
  rankFn = rankModelsForTask,
  initialRemainingUsd = null,
}: DecisionTreePanelProps) {
  const [task, setTask] = useState("deep_research");
  const [remainingRaw, setRemainingRaw] = useState(
    initialRemainingUsd === null || initialRemainingUsd === undefined
      ? ""
      : String(initialRemainingUsd),
  );
  const [promptCharsRaw, setPromptCharsRaw] = useState("4000");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DecisionTreeRankResponse | null>(null);

  const remainingParsed = useMemo(() => {
    const t = remainingRaw.trim();
    if (!t) return null;
    const n = Number(t);
    return Number.isFinite(n) ? n : null;
  }, [remainingRaw]);

  const promptCharsParsed = useMemo(() => {
    const t = promptCharsRaw.trim();
    if (!t) return null;
    const n = Number(t);
    return Number.isFinite(n) && n >= 0 ? Math.floor(n) : null;
  }, [promptCharsRaw]);

  async function onRank() {
    setBusy(true);
    setError(null);
    try {
      const body = await rankFn({
        task,
        models,
        remaining_usd: remainingParsed,
        prompt_chars: promptCharsParsed,
      });
      setResult(body);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const advisoryOk = result ? authorityIsAdvisory(result.authority) : true;

  return (
    <div data-testid="decision-tree-panel">
      <LemonCard title="Model decision tree" className="decision-tree-panel">
        <p
          className="text-sm opacity-80"
          data-testid="decision-tree-authority-blurb"
        >
          Advisory ranking only — this panel never dispatches a model. Production
          authority stays with you (NotDiamond / routers are not production
          dispatch).
        </p>

        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Task</span>
            <div data-testid="decision-tree-task">
              <LemonSelect
                value={task}
                onChange={(v) => setTask(String(v))}
                options={TASK_OPTIONS}
                aria-label="Decision tree task"
              />
            </div>
          </label>

          <label className="text-sm flex flex-col gap-1">
            <span>Remaining budget USD (leave empty if unknown)</span>
            <LemonInput
              value={remainingRaw}
              onChange={(e) => setRemainingRaw(e.target.value)}
              placeholder="unknown"
              data-testid="decision-tree-remaining"
              aria-label="Remaining budget USD"
            />
          </label>
          <div
            className="text-xs opacity-70"
            data-testid="decision-tree-remaining-display"
          >
            Remaining: {formatRemaining(remainingParsed)}
          </div>

          <label className="text-sm flex flex-col gap-1">
            <span>Proposed prompt size (characters)</span>
            <LemonInput
              value={promptCharsRaw}
              onChange={(e) => setPromptCharsRaw(e.target.value)}
              data-testid="decision-tree-prompt-chars"
              aria-label="Proposed prompt size in characters"
            />
          </label>

          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onRank()}
            data-testid="decision-tree-rank"
          >
            {busy ? "Ranking…" : "Rank models"}
          </LemonButton>

          {error ? (
            <div
              className="text-sm text-danger"
              data-testid="decision-tree-error"
            >
              {error}
            </div>
          ) : null}

          {result ? (
            <div data-testid="decision-tree-result">
              <div data-testid="decision-tree-authority">
                Authority: {result.authority}
                {!advisoryOk ? " (WARNING: non-advisory response)" : ""}
              </div>
              <div data-testid="decision-tree-recommended">
                Recommended: {result.recommended_model_id ?? "none"}
              </div>
              <div data-testid="decision-tree-result-remaining">
                Result remaining: {formatRemaining(result.remaining_usd)}
              </div>
              <ol className="mt-2" data-testid="decision-tree-ranked-list">
                {result.ranked.map((row) => (
                  <li key={row.model_id} data-testid={`ranked-${row.model_id}`}>
                    <strong>{row.model_id}</strong> ({row.tier}) score=
                    {row.score.toFixed(3)}
                    {" · "}proj {formatUsd(row.projected_cost_usd_low)}–
                    {formatUsd(row.projected_cost_usd_high)}
                    {" · "}
                    <span data-testid={`would-exceed-${row.model_id}`}>
                      {formatWouldExceed(row.would_exceed)}
                    </span>
                    <div className="text-xs opacity-70">{row.rationale}</div>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
