/**
 * SettingsAddModelInventoryPanel — add models (ids only) + budget bar.
 *
 * Free-file. secrets_stored/inventory_mutated/live_router always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeSettingsAddModelInventory,
  formatSettingsAddModelInventorySummary,
  type SettingsAddModelInventoryCompose,
} from "../../api/settingsAddModelInventoryCompose";

export interface SettingsAddModelInventoryPanelProps {
  composeFn?: typeof composeSettingsAddModelInventory;
}

export default function SettingsAddModelInventoryPanel({
  composeFn = composeSettingsAddModelInventory,
}: SettingsAddModelInventoryPanelProps) {
  const [pending, setPending] = useState("mimo-v2,claude-opus");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<SettingsAddModelInventoryCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const ids = pending
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      setResult(
        composeFn({
          models: [
            { model_id: "gpt-5.5", provider: "openai" },
            { model_id: "grok-4.5", provider: "xai" },
          ],
          pending_add_model_ids: ids,
          action: "propose_add",
          daily_cap_usd: 25,
          spent_usd: 3,
          selected_model_id: "gpt-5.5",
          projected_cost_usd_high: 0.4,
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="settings-add-model-inventory-panel">
      <LemonCard
        title="Settings · add model inventory (BYOK ids)"
        className="settings-add-model-inventory-panel"
      >
        <p className="text-sm opacity-80" data-testid="sami-blurb">
          Propose adding model ids to inventory with budget bar. Pure — never
          stores API keys or mutates settings store.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Pending model ids (comma-separated)</span>
            <LemonInput
              value={pending}
              onChange={(e) => setPending(e.target.value)}
              data-testid="sami-pending"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="sami-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="sami-compose"
          >
            Propose add models
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="sami-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="sami-result">
            <p data-testid="sami-summary">
              {formatSettingsAddModelInventorySummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>proposed_new={result.proposed_new_count}</li>
              <li>secrets_stored={String(result.secrets_stored)}</li>
              <li>inventory_mutated={String(result.inventory_mutated)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
