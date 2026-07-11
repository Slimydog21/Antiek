/**
 * Settings add-model inventory pack (pure).
 *
 * Operator vision: add models in settings (BYOK inventory ids only), see
 * budget usage bar, and optionally select a driver — never store secrets,
 * never auto-route.
 *
 * secrets_stored always false.
 * live_router_authorized always false.
 * inventory_mutated always false (pure propose only).
 */

import {
  composeSettingsModelInventoryBudget,
  type InventoryModelRow,
  type SettingsModelInventoryBudgetCompose,
} from "./settingsModelInventoryBudgetCompose";
import {
  composeSettingsDecisionTreeUsageBar,
  type SettingsDecisionTreeUsageBarCompose,
} from "./settingsDecisionTreeUsageBarCompose";
import type { ModelOption } from "./modelDecisionPromptCompose";

export type AddModelAction = "preview" | "propose_add";

export interface SettingsAddModelInventoryInput {
  /** Current inventory (ids only). */
  models: InventoryModelRow[];
  /**
   * Model ids operator wants to add (BYOK). Rejected if secret-like.
   * For propose_add, these become the proposed inventory extension.
   */
  pending_add_model_ids: string[];
  action: AddModelAction;
  daily_cap_usd: number | null;
  spent_usd: number | null;
  selected_model_id?: string | null;
  projected_cost_usd_high?: number | null;
  projected_cost_usd_low?: number | null;
  operator_ack: boolean;
}

export interface SettingsAddModelInventoryCompose {
  inventory: SettingsModelInventoryBudgetCompose;
  decision_tree: SettingsDecisionTreeUsageBarCompose | null;
  action: AddModelAction;
  /** Ids that would be added (not already in inventory). */
  proposed_new_model_ids: string[];
  proposed_new_count: number;
  /**
   * True when operator_ack and (preview with valid inventory OR propose_add
   * with ≥1 new id). Still never mutates stored inventory.
   */
  pack_ready: boolean;
  secrets_stored: false;
  live_router_authorized: false;
  /** Always false — pure layer never writes settings inventory. */
  inventory_mutated: false;
  notes: string[];
  authority: "settings_add_model_inventory_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function requireModelId(value: unknown, name: string): string {
  const id = requireNonEmpty(value, name);
  if (
    id.length > 128 ||
    /sk-|api[_-]?key|secret|bearer\s/i.test(id) ||
    id.includes(" ")
  ) {
    throw new Error(`${name} must be a model id, not secret material`);
  }
  return id;
}

/**
 * Compose settings add-model inventory + optional decision tree pack.
 * Never stores secrets; never mutates inventory; never live-routes.
 */
export function composeSettingsAddModelInventory(
  input: SettingsAddModelInventoryInput,
): SettingsAddModelInventoryCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (input.action !== "preview" && input.action !== "propose_add") {
    throw new Error("action must be preview or propose_add");
  }
  if (!Array.isArray(input.pending_add_model_ids)) {
    throw new Error("pending_add_model_ids must be an array");
  }

  const notes: string[] = [
    "secrets_stored=false — model ids only; never raw API keys",
    "live_router_authorized=false — operator selects model",
    "inventory_mutated=false — propose_add is intent only",
  ];

  const inventory = composeSettingsModelInventoryBudget({
    models: input.models,
    pending_add_model_ids: input.pending_add_model_ids,
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
    selected_model_id: input.selected_model_id,
  });
  notes.push(...inventory.notes.map((n) => `[inventory] ${n}`));

  const existing = new Set(inventory.model_ids);
  const proposed_new_model_ids: string[] = [];
  const seen = new Set<string>();
  for (let i = 0; i < input.pending_add_model_ids.length; i++) {
    const id = requireModelId(
      input.pending_add_model_ids[i],
      `pending_add_model_ids[${i}]`,
    );
    if (seen.has(id)) continue;
    seen.add(id);
    if (!existing.has(id)) {
      proposed_new_model_ids.push(id);
    }
  }
  notes.push(
    `proposed_new_count=${proposed_new_model_ids.length} (not yet in inventory)`,
  );

  // Decision tree uses current inventory models; if propose_add and new ids,
  // surface them as ModelOptions for selection preview only.
  let decision_tree: SettingsDecisionTreeUsageBarCompose | null = null;
  const modelOptions: ModelOption[] = input.models.map((m) => ({
    model_id: m.model_id,
    tier: m.tier ?? undefined,
  }));
  if (input.action === "propose_add") {
    for (const id of proposed_new_model_ids) {
      modelOptions.push({ model_id: id, tier: "pending_add" });
    }
  }

  if (modelOptions.length > 0) {
    const selected =
      input.selected_model_id != null &&
      String(input.selected_model_id).trim() !== ""
        ? requireModelId(input.selected_model_id, "selected_model_id")
        : modelOptions[0].model_id;
    // selected must be in options for decision tree
    const ids = new Set(modelOptions.map((m) => m.model_id));
    const selected_final = ids.has(selected)
      ? selected
      : modelOptions[0].model_id;

    decision_tree = composeSettingsDecisionTreeUsageBar({
      selected_model_id: selected_final,
      models: modelOptions,
      daily_cap_usd: input.daily_cap_usd,
      spent_usd: input.spent_usd,
      projected_cost_usd_high: input.projected_cost_usd_high,
      projected_cost_usd_low: input.projected_cost_usd_low,
      pending_add_model_ids: input.pending_add_model_ids,
      operator_ack: input.operator_ack,
    });
    notes.push(...decision_tree.notes.map((n) => `[decision] ${n}`));
  } else {
    notes.push("decision_tree skipped — empty inventory and no pending adds");
  }

  let pack_ready = false;
  if (input.action === "preview") {
    pack_ready =
      input.operator_ack === true &&
      inventory.inventory_count >= 0 &&
      inventory.secrets_stored === false;
    notes.push(
      pack_ready
        ? "pack_ready=true — inventory preview advisory"
        : "pack_ready=false — operator_ack required for preview pack",
    );
  } else {
    // propose_add
    if (proposed_new_model_ids.length === 0) {
      notes.push(
        "pack_ready=false — propose_add requires ≥1 new model id not already inventoried",
      );
      pack_ready = false;
    } else if (!input.operator_ack) {
      notes.push("pack_ready=false — propose_add requires operator_ack");
      pack_ready = false;
    } else {
      pack_ready = true;
      notes.push(
        "pack_ready=true — propose_add intent ready; inventory_mutated=false",
      );
    }
  }

  if (
    inventory.secrets_stored !== false ||
    inventory.live_router_authorized !== false ||
    (decision_tree != null &&
      (decision_tree.secrets_stored !== false ||
        decision_tree.live_router_authorized !== false))
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("secrets_stored=false");
  notes.push("live_router_authorized=false");
  notes.push("inventory_mutated=false");

  return {
    inventory,
    decision_tree,
    action: input.action,
    proposed_new_model_ids,
    proposed_new_count: proposed_new_model_ids.length,
    pack_ready,
    secrets_stored: false,
    live_router_authorized: false,
    inventory_mutated: false,
    notes,
    authority: "settings_add_model_inventory_compose_advisory",
  };
}

export function formatSettingsAddModelInventorySummary(
  c: SettingsAddModelInventoryCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · action=${c.action} · ` +
    `inventory=${c.inventory.inventory_count} · ` +
    `proposed_new=${c.proposed_new_count} · ` +
    `secrets_stored=false · inventory_mutated=false · live_router_authorized=false`
  );
}
