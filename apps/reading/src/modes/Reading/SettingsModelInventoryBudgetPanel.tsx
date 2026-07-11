/**
 * SettingsModelInventoryBudgetPanel — inventory + usage bar.
 *
 * Free-file. secrets_stored and live_router_authorized always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeSettingsModelInventoryBudget,
  formatSettingsModelInventoryBudgetSummary,
  type SettingsModelInventoryBudgetCompose,
} from "../../api/settingsModelInventoryBudgetCompose";

export interface SettingsModelInventoryBudgetPanelProps {
  composeFn?: typeof composeSettingsModelInventoryBudget;
}

export default function SettingsModelInventoryBudgetPanel({
  composeFn = composeSettingsModelInventoryBudget,
}: SettingsModelInventoryBudgetPanelProps) {
  const [modelsRaw, setModelsRaw] = useState("gpt-5,claude-opus");
  const [pending, setPending] = useState("mimo-pro");
  const [cap, setCap] = useState("50");
  const [spent, setSpent] = useState("12.5");
  const [selected, setSelected] = useState("gpt-5");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<SettingsModelInventoryBudgetCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const models = modelsRaw
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .map((model_id) => ({ model_id }));
      const pending_add = pending
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      setResult(
        composeFn({
          models,
          pending_add_model_ids: pending_add.length ? pending_add : null,
          daily_cap_usd: cap.trim() === "" ? null : Number(cap),
          spent_usd: spent.trim() === "" ? null : Number(spent),
          selected_model_id: selected.trim() || null,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="settings-model-inventory-budget-panel">
      <LemonCard
        title="Settings · model inventory + budget bar"
        className="settings-model-inventory-budget-panel"
      >
        <p className="text-sm opacity-80" data-testid="smib-blurb">
          Add model ids (no secrets) and display usage vs daily cap. Pure —
          secrets_stored and live_router_authorized stay false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Inventory model ids (comma)</span>
            <LemonInput
              value={modelsRaw}
              onChange={(e) => setModelsRaw(e.target.value)}
              data-testid="smib-models"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Pending add ids</span>
            <LemonInput
              value={pending}
              onChange={(e) => setPending(e.target.value)}
              data-testid="smib-pending"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Daily cap USD</span>
            <LemonInput
              value={cap}
              onChange={(e) => setCap(e.target.value)}
              data-testid="smib-cap"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Spent USD</span>
            <LemonInput
              value={spent}
              onChange={(e) => setSpent(e.target.value)}
              data-testid="smib-spent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Selected model</span>
            <LemonInput
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              data-testid="smib-selected"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="smib-compose"
          >
            Compose inventory + budget
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="smib-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="smib-result"
            >
              <div data-testid="smib-inv">
                inventory_count={result.inventory_count}
              </div>
              <div data-testid="smib-secrets">
                secrets_stored={String(result.secrets_stored)}
              </div>
              <div data-testid="smib-router">
                live_router_authorized=
                {String(result.live_router_authorized)}
              </div>
              <div data-testid="smib-remaining">
                remaining_usd=
                {result.bar.remaining_usd === null
                  ? "null"
                  : String(result.bar.remaining_usd)}
              </div>
              <div data-testid="smib-summary">
                {formatSettingsModelInventoryBudgetSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
