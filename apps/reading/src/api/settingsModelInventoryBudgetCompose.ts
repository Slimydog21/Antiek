/**
 * Settings model inventory + budget bar compose (pure).
 *
 * Operator vision: add models in settings (ids only / BYOK inventory), see
 * usage bar against daily budget. Never stores secrets; never auto-routes.
 *
 * secrets_stored always false.
 * live_router_authorized always false.
 */

import { computeUsageBar, type UsageBarSnapshot } from "./promptProjection";

export interface InventoryModelRow {
  model_id: string;
  tier?: string | null;
  /** Provider label only — never credentials. */
  provider?: string | null;
}

export interface SettingsModelInventoryBudgetInput {
  models: InventoryModelRow[];
  /**
   * Models pending add (ids only). Rejected if secret-like.
   */
  pending_add_model_ids?: string[] | null;
  daily_cap_usd: number | null;
  spent_usd: number | null;
  selected_model_id?: string | null;
}

export interface SettingsModelInventoryBudgetCompose {
  inventory_count: number;
  pending_add_count: number;
  model_ids: string[];
  selected_model_id: string | null;
  selected_in_inventory: boolean | null;
  bar: UsageBarSnapshot;
  /** Always false — never accept or store API keys. */
  secrets_stored: false;
  /** Always false — operator selects model; no auto-router. */
  live_router_authorized: false;
  notes: string[];
  authority: "settings_model_inventory_budget_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function requireModelId(value: unknown, name: string): string {
  const id = requireNonEmpty(value, name);
  if (id.length > 128 || /sk-|api[_-]?key|secret|bearer\s/i.test(id) || id.includes(" ")) {
    throw new Error(`${name} must be a model id, not secret material`);
  }
  return id;
}

/**
 * Compose settings inventory + usage bar snapshot.
 * Never stores secrets; never authorizes live routing.
 */
export function composeSettingsModelInventoryBudget(
  input: SettingsModelInventoryBudgetInput,
): SettingsModelInventoryBudgetCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (!Array.isArray(input.models)) {
    throw new Error("models must be an array");
  }

  const notes: string[] = [
    "secrets_stored=false — model ids/inventory only; never raw API keys",
    "live_router_authorized=false — operator selects model",
  ];

  const model_ids: string[] = [];
  const seen = new Set<string>();
  for (let i = 0; i < input.models.length; i++) {
    const m = input.models[i];
    if (!m || typeof m !== "object") {
      throw new Error(`models[${i}] must be an object`);
    }
    const id = requireModelId(m.model_id, `models[${i}].model_id`);
    if (seen.has(id)) {
      throw new Error(`duplicate model_id: ${id}`);
    }
    seen.add(id);
    model_ids.push(id);
    if (m.provider != null) {
      const prov = requireNonEmpty(m.provider, `models[${i}].provider`);
      if (/sk-|api[_-]?key|secret/i.test(prov)) {
        throw new Error(`models[${i}].provider must not contain secret material`);
      }
    }
  }

  let pending_add_count = 0;
  if (input.pending_add_model_ids != null) {
    if (!Array.isArray(input.pending_add_model_ids)) {
      throw new Error("pending_add_model_ids must be an array when set");
    }
    const pseen = new Set<string>();
    for (let i = 0; i < input.pending_add_model_ids.length; i++) {
      const id = requireModelId(
        input.pending_add_model_ids[i],
        `pending_add_model_ids[${i}]`,
      );
      if (pseen.has(id)) {
        throw new Error(`duplicate pending_add_model_id: ${id}`);
      }
      pseen.add(id);
      if (seen.has(id)) {
        notes.push(`pending ${id} already in inventory`);
      }
    }
    pending_add_count = pseen.size;
    notes.push(`pending_add_count=${pending_add_count} (ids only)`);
  }

  const inventory_count = model_ids.length;
  notes.push(`inventory_count=${inventory_count}`);

  let selected_model_id: string | null = null;
  let selected_in_inventory: boolean | null = null;
  if (
    input.selected_model_id != null &&
    input.selected_model_id !== undefined
  ) {
    selected_model_id = requireModelId(
      input.selected_model_id,
      "selected_model_id",
    );
    selected_in_inventory = seen.has(selected_model_id);
    notes.push(
      selected_in_inventory
        ? `selected_model_id=${selected_model_id} in inventory`
        : `selected_model_id=${selected_model_id} not in inventory`,
    );
  }

  const bar = computeUsageBar({
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
    spend_basis: "settings_budget_display",
  });
  notes.push(...bar.notes);

  notes.push("secrets_stored=false");
  notes.push("live_router_authorized=false");

  return {
    inventory_count,
    pending_add_count,
    model_ids,
    selected_model_id,
    selected_in_inventory,
    bar,
    secrets_stored: false,
    live_router_authorized: false,
    notes,
    authority: "settings_model_inventory_budget_compose_advisory",
  };
}

export function formatSettingsModelInventoryBudgetSummary(
  c: SettingsModelInventoryBudgetCompose,
): string {
  return (
    `inventory=${c.inventory_count} · pending_add=${c.pending_add_count} · ` +
    `remaining=${c.bar.remaining_usd} · secrets_stored=false · live_router_authorized=false`
  );
}
