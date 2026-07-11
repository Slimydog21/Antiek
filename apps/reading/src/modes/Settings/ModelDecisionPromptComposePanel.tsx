/**
 * ModelDecisionPromptComposePanel - model pick + budget projection compose.
 *
 * Free-file Settings panel. Pure client; no live meters.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeModelDecisionWithProjection,
  formatComposeSummary,
  type ModelDecisionPromptComposeResult,
} from "../../api/modelDecisionPromptCompose";

export interface ModelDecisionPromptComposePanelProps {
  composeFn?: typeof composeModelDecisionWithProjection;
  initialModelsJson?: string;
  initialSelected?: string;
  initialCap?: string;
  initialSpent?: string;
}

export default function ModelDecisionPromptComposePanel({
  composeFn = composeModelDecisionWithProjection,
  initialModelsJson = '[{"model_id":"flash-1","tier":"flash","projected_cost_usd_high":0.5,"projected_cost_usd_low":0.1},{"model_id":"pro-1","tier":"pro","projected_cost_usd_high":3,"projected_cost_usd_low":1}]',
  initialSelected = "flash-1",
  initialCap = "10",
  initialSpent = "2",
}: ModelDecisionPromptComposePanelProps) {
  const [modelsJson, setModelsJson] = useState(initialModelsJson);
  const [selected, setSelected] = useState(initialSelected);
  const [capRaw, setCapRaw] = useState(initialCap);
  const [spentRaw, setSpentRaw] = useState(initialSpent);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<ModelDecisionPromptComposeResult | null>(null);

  function parseOptionalNumber(raw: string): number | null {
    const t = raw.trim();
    if (!t) return null;
    const n = Number(t);
    if (!Number.isFinite(n)) {
      throw new Error("money field must be finite or blank");
    }
    return n;
  }

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const models = JSON.parse(modelsJson) as unknown;
      if (!Array.isArray(models)) {
        throw new Error("models JSON must be an array");
      }
      setResult(
        composeFn({
          selected_model_id: selected.trim(),
          models: models as Parameters<typeof composeFn>[0]["models"],
          daily_cap_usd: parseOptionalNumber(capRaw),
          spent_usd: parseOptionalNumber(spentRaw),
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="model-decision-prompt-compose-panel">
      <LemonCard
        title="Model decision + prompt projection"
        className="model-decision-prompt-compose-panel"
      >
        <p className="text-sm opacity-80" data-testid="mdpc-blurb">
          Select a model and project how the proposed prompt would affect
          remaining budget. Unknown remaining or high cost yields
          would_exceed=null (never invents safe).
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Selected model id</span>
            <LemonInput
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              data-testid="mdpc-selected"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Models inventory JSON</span>
            <textarea
              value={modelsJson}
              onChange={(e) => setModelsJson(e.target.value)}
              data-testid="mdpc-models"
              className="border border-border rounded px-2 py-1 text-sm min-h-[5rem] font-mono"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Daily cap USD (blank = unknown)</span>
            <LemonInput
              value={capRaw}
              onChange={(e) => setCapRaw(e.target.value)}
              data-testid="mdpc-cap"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Spent USD (blank = unknown)</span>
            <LemonInput
              value={spentRaw}
              onChange={(e) => setSpentRaw(e.target.value)}
              data-testid="mdpc-spent"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="mdpc-run"
          >
            Compose decision + projection
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="mdpc-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="mdpc-result" className="text-sm flex flex-col gap-1">
              <div data-testid="mdpc-summary">{formatComposeSummary(result)}</div>
              <div data-testid="mdpc-would-exceed">
                would_exceed=
                {result.would_exceed === null
                  ? "null"
                  : String(result.would_exceed)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
