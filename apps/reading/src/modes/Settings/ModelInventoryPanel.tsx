/**
 * ModelInventoryPanel — show configured models for decision-tree selection.
 *
 * Pure presentation over #791 inventoryToDecisionModels. Caller injects rows
 * (or a loadFn); this panel does not own settings HTTP or Settings/index.
 * ready=false models remain visible so gaps are honest.
 */

import { useMemo, useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  inventoryToDecisionModels,
  type InventoryModelRow,
} from "../../api/modelDecisionInventory";
import type { DecisionModelIn } from "../../api/modelDecision";

export interface ModelInventoryPanelProps {
  /** Static rows (tests / parent-provided inventory). */
  rows?: InventoryModelRow[] | null;
  /** Optional async loader; result re-validated via inventoryToDecisionModels. */
  loadFn?: () => Promise<InventoryModelRow[] | unknown>;
  /** Called when operator picks a model_id for a prompt. */
  onSelectModel?: (model: DecisionModelIn) => void;
}

function parseRows(raw: unknown): InventoryModelRow[] {
  if (!Array.isArray(raw)) {
    throw new Error("model inventory rejected: rows must be an array");
  }
  const out: InventoryModelRow[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") {
      throw new Error("model inventory rejected: every row must be an object");
    }
    const o = item as Record<string, unknown>;
    if (typeof o.provider_id !== "string" || !o.provider_id.trim()) {
      throw new Error("model inventory rejected: provider_id required");
    }
    if (typeof o.ready !== "boolean") {
      throw new Error("model inventory rejected: ready must be boolean (no invent)");
    }
    out.push({
      provider_id: o.provider_id.trim(),
      ready: o.ready,
      tier_bindings: Array.isArray(o.tier_bindings)
        ? o.tier_bindings.map((t) => String(t))
        : null,
      primary_model:
        typeof o.primary_model === "string" ? o.primary_model : null,
      notes: typeof o.notes === "string" ? o.notes : null,
    });
  }
  return out;
}

export default function ModelInventoryPanel({
  rows = null,
  loadFn,
  onSelectModel,
}: ModelInventoryPanelProps) {
  const [loaded, setLoaded] = useState<InventoryModelRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  // Validate both loadFn results and direct `rows` props — never pass
  // untyped ready values into inventoryToDecisionModels (Boolean() invents).
  const { models, rowsError } = useMemo(() => {
    const source = loaded ?? rows;
    if (source == null) {
      return { models: [] as ReturnType<typeof inventoryToDecisionModels>, rowsError: null as string | null };
    }
    try {
      const validated = parseRows(source);
      return { models: inventoryToDecisionModels(validated), rowsError: null as string | null };
    } catch (e) {
      return {
        models: [] as ReturnType<typeof inventoryToDecisionModels>,
        rowsError: e instanceof Error ? e.message : String(e),
      };
    }
  }, [loaded, rows]);

  const displayError = error ?? rowsError;

  async function onLoad() {
    if (!loadFn) return;
    setBusy(true);
    setError(null);
    try {
      const raw = await loadFn();
      setLoaded(parseRows(raw));
    } catch (e) {
      setLoaded(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function pick(m: DecisionModelIn) {
    setSelected(m.model_id);
    onSelectModel?.(m);
  }

  return (
    <div data-testid="model-inventory-panel">
      <LemonCard title="Model inventory" className="model-inventory-panel">
        <p className="text-sm opacity-80" data-testid="model-inventory-blurb">
          Models available for any given prompt. Not-ready providers stay listed
          so gaps are visible. Selection is advisory until the decision tree
          ranks them — this panel does not call providers.
        </p>

        {loadFn ? (
          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onLoad()}
            data-testid="model-inventory-load"
            className="mt-2"
          >
            {busy ? "Loading…" : "Load inventory"}
          </LemonButton>
        ) : null}

        {displayError ? (
          <div className="text-sm text-danger mt-2" data-testid="model-inventory-error">
            {displayError}
          </div>
        ) : null}

        {!displayError && models.length === 0 ? (
          <div className="text-sm mt-3" data-testid="model-inventory-empty">
            No rankable models (empty inventory or missing primary_model).
          </div>
        ) : null}

        {!displayError && models.length > 0 ? (
          <ul className="mt-3 flex flex-col gap-2" data-testid="model-inventory-list">
            {models.map((m) => (
              <li
                key={`${m.provider}:${m.model_id}`}
                data-testid={`model-inventory-row-${m.model_id}`}
                data-ready={m.enabled ? "true" : "false"}
                className="flex items-center justify-between gap-2 text-sm rounded border border-border px-2 py-1"
              >
                <div>
                  <div data-testid={`model-inventory-id-${m.model_id}`}>
                    {m.model_id}
                  </div>
                  <div className="text-xs opacity-70">
                    {m.provider} · tier={m.tier} ·{" "}
                    {m.enabled ? "ready" : "not ready"}
                  </div>
                </div>
                <LemonButton
                  disabled={!m.enabled}
                  onClick={() => pick(m)}
                  data-testid={`model-inventory-select-${m.model_id}`}
                >
                  {selected === m.model_id ? "Selected" : "Select"}
                </LemonButton>
              </li>
            ))}
          </ul>
        ) : null}

        {selected ? (
          <div className="text-sm mt-2" data-testid="model-inventory-selected">
            Selected: {selected}
          </div>
        ) : null}
      </LemonCard>
    </div>
  );
}
