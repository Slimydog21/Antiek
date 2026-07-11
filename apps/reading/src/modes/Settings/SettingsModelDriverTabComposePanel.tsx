/**
 * SettingsModelDriverTabComposePanel - decision tree tab compose snapshot.
 *
 * Free-file. live_router_authorized and secrets_stored always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeSettingsModelDriverTab,
  formatSettingsModelDriverTabSummary,
  type SettingsModelDriverTabCompose,
} from "../../api/settingsModelDriverTabCompose";

export interface SettingsModelDriverTabComposePanelProps {
  composeFn?: typeof composeSettingsModelDriverTab;
}

export default function SettingsModelDriverTabComposePanel({
  composeFn = composeSettingsModelDriverTab,
}: SettingsModelDriverTabComposePanelProps) {
  const [modelsJson, setModelsJson] = useState(
    '[{"model_id":"flash-1","tier":"flash","projected_cost_usd_high":0.5,"projected_cost_usd_low":0.1},{"model_id":"pro-1","tier":"pro","projected_cost_usd_high":3,"projected_cost_usd_low":1}]',
  );
  const [selected, setSelected] = useState("flash-1");
  const [capRaw, setCapRaw] = useState("10");
  const [spentRaw, setSpentRaw] = useState("2");
  const [focusTask, setFocusTask] = useState("deep_research");
  const [benchBest, setBenchBest] = useState("pro-1");
  const [ndModel, setNdModel] = useState("pro-1");
  const [ndKill, setNdKill] = useState(false);
  const [pendingAdd, setPendingAdd] = useState("local-llama");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<SettingsModelDriverTabCompose | null>(null);

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
      const models = JSON.parse(modelsJson);
      if (!Array.isArray(models)) {
        throw new Error("models JSON must be an array");
      }
      const pending = pendingAdd
        .split(/[,\n]/)
        .map((s) => s.trim())
        .filter(Boolean);
      setResult(
        composeFn({
          selected_model_id: selected.trim(),
          models: models as Parameters<typeof composeFn>[0]["models"],
          daily_cap_usd: parseOptionalNumber(capRaw),
          spent_usd: parseOptionalNumber(spentRaw),
          focus_task: focusTask.trim() || null,
          bench_bests: focusTask.trim()
            ? [
                {
                  task: focusTask.trim(),
                  best_model_id: benchBest.trim(),
                  score: 0.9,
                },
              ]
            : null,
          nd_shadow: ndModel.trim()
            ? {
                recommended_model_id: ndModel.trim(),
                kill_switch_on: ndKill,
              }
            : null,
          pending_add_model_ids: pending.length ? pending : null,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="settings-model-driver-tab-compose-panel">
      <LemonCard
        title="Settings · model driver tab"
        className="settings-model-driver-tab-compose-panel"
      >
        <p className="text-sm opacity-80" data-testid="smdt-blurb">
          Decision-tree model selection with usage bar, prompt projection,
          optional Antiek-bench best, and NotDiamond shadow (advisory only).
          live_router_authorized and secrets_stored stay false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Models inventory JSON</span>
            <textarea
              value={modelsJson}
              onChange={(e) => setModelsJson(e.target.value)}
              data-testid="smdt-models"
              className="border border-border rounded px-2 py-1 text-sm min-h-[4rem] font-mono"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Selected model id</span>
            <LemonInput
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              data-testid="smdt-selected"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Daily cap USD</span>
            <LemonInput
              value={capRaw}
              onChange={(e) => setCapRaw(e.target.value)}
              data-testid="smdt-cap"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Spent USD</span>
            <LemonInput
              value={spentRaw}
              onChange={(e) => setSpentRaw(e.target.value)}
              data-testid="smdt-spent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Focus task (bench)</span>
            <LemonInput
              value={focusTask}
              onChange={(e) => setFocusTask(e.target.value)}
              data-testid="smdt-focus"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Bench best model id</span>
            <LemonInput
              value={benchBest}
              onChange={(e) => setBenchBest(e.target.value)}
              data-testid="smdt-bench-best"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>ND shadow model id</span>
            <LemonInput
              value={ndModel}
              onChange={(e) => setNdModel(e.target.value)}
              data-testid="smdt-nd"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ndKill}
              onChange={(e) => setNdKill(e.target.checked)}
              data-testid="smdt-nd-kill"
            />
            ND kill_switch_on
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Pending add model ids (comma-separated, no secrets)</span>
            <LemonInput
              value={pendingAdd}
              onChange={(e) => setPendingAdd(e.target.value)}
              data-testid="smdt-pending"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="smdt-compose"
          >
            Compose driver tab
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="smdt-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div
              data-testid="smdt-result"
              className="text-sm flex flex-col gap-1"
            >
              <div data-testid="smdt-summary">
                {formatSettingsModelDriverTabSummary(result)}
              </div>
              <div data-testid="smdt-router">
                live_router_authorized=
                {String(result.live_router_authorized)}
              </div>
              <div data-testid="smdt-secrets">
                secrets_stored={String(result.secrets_stored)}
              </div>
              <div data-testid="smdt-ready">
                tab_ready={String(result.tab_ready)}
              </div>
              <div data-testid="smdt-would">
                would_exceed=
                {result.decision.would_exceed === null
                  ? "null"
                  : String(result.decision.would_exceed)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
