/**
 * SettingsDecisionTreeUsageBarPanel — model decision tree + usage bar.
 *
 * Free-file. live_router_authorized, secrets_stored, live_meter_read always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeSettingsDecisionTreeUsageBar,
  formatSettingsDecisionTreeUsageBarSummary,
  type SettingsDecisionTreeUsageBarCompose,
} from "../../api/settingsDecisionTreeUsageBarCompose";

export interface SettingsDecisionTreeUsageBarPanelProps {
  composeFn?: typeof composeSettingsDecisionTreeUsageBar;
}

export default function SettingsDecisionTreeUsageBarPanel({
  composeFn = composeSettingsDecisionTreeUsageBar,
}: SettingsDecisionTreeUsageBarPanelProps) {
  const [modelId, setModelId] = useState("gpt-5");
  const [cap, setCap] = useState("100");
  const [spent, setSpent] = useState("40");
  const [projHigh, setProjHigh] = useState("2");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<SettingsDecisionTreeUsageBarCompose | null>(null);

  function parseMoney(raw: string): number | null {
    const t = raw.trim();
    if (!t) return null;
    const n = Number(t);
    if (!Number.isFinite(n)) throw new Error("money fields must be finite numbers");
    return n;
  }

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          selected_model_id: modelId.trim(),
          models: [
            {
              model_id: "gpt-5",
              tier: "frontier",
              projected_cost_usd_high: 2,
            },
            {
              model_id: "composer-2.5",
              tier: "workhorse",
              projected_cost_usd_high: 0.5,
            },
          ],
          daily_cap_usd: parseMoney(cap),
          spent_usd: parseMoney(spent),
          projected_cost_usd_high: parseMoney(projHigh),
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="settings-decision-tree-usage-bar-panel">
      <LemonCard
        title="Settings · decision tree + usage bar"
        className="settings-decision-tree-usage-bar-panel"
      >
        <p className="text-sm opacity-80" data-testid="sdtub-blurb">
          Select a model, see usage against budget, and project prompt impact
          before send. Pure advisory — no live router, no secrets.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Selected model</span>
            <select
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              data-testid="sdtub-model"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="gpt-5">gpt-5</option>
              <option value="composer-2.5">composer-2.5</option>
            </select>
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Daily cap USD</span>
            <LemonInput
              value={cap}
              onChange={(e) => setCap(e.target.value)}
              data-testid="sdtub-cap"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Spent USD</span>
            <LemonInput
              value={spent}
              onChange={(e) => setSpent(e.target.value)}
              data-testid="sdtub-spent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Projected cost high USD</span>
            <LemonInput
              value={projHigh}
              onChange={(e) => setProjHigh(e.target.value)}
              data-testid="sdtub-proj"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="sdtub-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="sdtub-compose"
          >
            Compose decision tree + usage bar
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="sdtub-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="sdtub-result"
            >
              <div data-testid="sdtub-ready">
                decision_ready={String(result.decision_ready)}
              </div>
              <div data-testid="sdtub-usage">
                usage_percent=
                {result.usage_percent === null
                  ? "null"
                  : String(result.usage_percent)}
              </div>
              <div data-testid="sdtub-would">
                would_exceed=
                {result.would_exceed === null
                  ? "null"
                  : String(result.would_exceed)}
              </div>
              <div data-testid="sdtub-router">
                live_router_authorized=
                {String(result.live_router_authorized)}
              </div>
              <div data-testid="sdtub-secrets">
                secrets_stored={String(result.secrets_stored)}
              </div>
              <div data-testid="sdtub-meter">
                live_meter_read={String(result.live_meter_read)}
              </div>
              <div data-testid="sdtub-summary">
                {formatSettingsDecisionTreeUsageBarSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
