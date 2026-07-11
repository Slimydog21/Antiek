/**
 * NotDiamond shadow advisory compose (pure).
 *
 * Operator: investigate NotDiamond as router. Decision (platform §16):
 * REJECT as production router. Useful only as shadow/advisory signal next to
 * the operator model decision tree.
 *
 * live_router_authorized is always false.
 * Never rewrites the selected model; never stores secrets; never calls ND API.
 */

export interface NotDiamondShadowAdvisoryInput {
  /** Operator-selected model id (authority). */
  selected_model_id: string;
  /**
   * ND recommended model id — caller-supplied shadow only.
   * Never invents a recommendation.
   */
  nd_recommended_model_id: string | null;
  /**
   * Kill switch must be explicit. When true, shadow is suppressed entirely.
   * Default production posture: kill switch on unless operator opts into shadow.
   */
  kill_switch_on: boolean;
  /** Optional confidence 0..1 from ND shadow log (caller-supplied). */
  confidence?: number | null;
  /** Optional task family for display (e.g. deep_research). */
  task?: string | null;
  /**
   * Inventory of known model ids. When set, recommended must be in inventory
   * to be displayable (fail closed on unknown ids).
   */
  inventory_model_ids?: string[] | null;
}

export interface NotDiamondShadowAdvisoryCompose {
  selected_model_id: string;
  nd_recommended_model_id: string | null;
  /** True when kill switch off, rec present, and inventory OK (if provided). */
  shadow_visible: boolean;
  /** True when visible and rec !== selected. Null when not visible. */
  differs_from_selected: boolean | null;
  /**
   * Soft suggestion only — operator may choose to switch. Never auto-applied.
   * Always null when kill_switch_on or shadow not visible.
   */
  suggested_model_id: string | null;
  confidence: number | null;
  task: string | null;
  /**
   * Platform decision artifact: production router is REJECTED.
   * Always the string "REJECT" in this pure layer.
   */
  production_router_verdict: "REJECT";
  /** Always false — ND never becomes live routing authority. */
  live_router_authorized: false;
  notes: string[];
  authority: "notdiamond_shadow_advisory_only";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose NotDiamond shadow advisory snapshot for the model decision tree.
 * Never authorizes live routing; never mutates selection.
 */
export function composeNotDiamondShadowAdvisory(
  input: NotDiamondShadowAdvisoryInput,
): NotDiamondShadowAdvisoryCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.kill_switch_on !== "boolean") {
    throw new Error("kill_switch_on must be an explicit boolean");
  }
  const selected_model_id = requireNonEmpty(
    input.selected_model_id,
    "selected_model_id",
  );

  const notes: string[] = [
    "production_router_verdict=REJECT — NotDiamond is not production router (§16)",
    "live_router_authorized=false — operator model decision remains authority",
    "shadow is advisory only; never auto-routes",
  ];

  let confidence: number | null = null;
  if (input.confidence !== undefined && input.confidence !== null) {
    if (
      typeof input.confidence !== "number" ||
      !Number.isFinite(input.confidence) ||
      input.confidence < 0 ||
      input.confidence > 1
    ) {
      throw new Error("confidence must be finite in [0, 1] when set");
    }
    confidence = input.confidence;
  }

  let task: string | null = null;
  if (input.task != null && input.task !== undefined) {
    task = requireNonEmpty(input.task, "task");
  }

  let inventory: Set<string> | null = null;
  if (input.inventory_model_ids != null) {
    if (!Array.isArray(input.inventory_model_ids)) {
      throw new Error("inventory_model_ids must be an array when set");
    }
    inventory = new Set<string>();
    for (let i = 0; i < input.inventory_model_ids.length; i++) {
      const id = requireNonEmpty(
        input.inventory_model_ids[i],
        `inventory_model_ids[${i}]`,
      );
      if (id.length > 128 || /sk-|api[_-]?key|secret/i.test(id)) {
        throw new Error(
          `inventory_model_ids[${i}] must be a model id, not secret material`,
        );
      }
      inventory.add(id);
    }
    if (!inventory.has(selected_model_id)) {
      throw new Error(
        "selected_model_id must be present in inventory_model_ids when inventory is set",
      );
    }
    notes.push(`inventory_count=${inventory.size}`);
  }

  let nd_recommended_model_id: string | null = null;
  if (
    input.nd_recommended_model_id != null &&
    input.nd_recommended_model_id !== undefined
  ) {
    nd_recommended_model_id = requireNonEmpty(
      input.nd_recommended_model_id,
      "nd_recommended_model_id",
    );
    if (
      nd_recommended_model_id.length > 128 ||
      /sk-|api[_-]?key|secret/i.test(nd_recommended_model_id)
    ) {
      throw new Error(
        "nd_recommended_model_id must be a model id, not secret material",
      );
    }
  }

  let shadow_visible = false;
  let differs_from_selected: boolean | null = null;
  let suggested_model_id: string | null = null;

  if (input.kill_switch_on) {
    notes.push(
      "kill_switch_on=true — shadow suppressed (safe default; operator must opt in)",
    );
    shadow_visible = false;
  } else if (nd_recommended_model_id === null) {
    notes.push(
      "kill_switch_on=false but nd_recommended_model_id null — no invent shadow",
    );
    shadow_visible = false;
  } else if (inventory !== null && !inventory.has(nd_recommended_model_id)) {
    notes.push(
      `nd_recommended_model_id=${nd_recommended_model_id} not in inventory — shadow suppressed (fail closed)`,
    );
    shadow_visible = false;
  } else {
    shadow_visible = true;
    differs_from_selected = nd_recommended_model_id !== selected_model_id;
    // Soft suggestion only when differs; still never auto-applies.
    suggested_model_id = differs_from_selected
      ? nd_recommended_model_id
      : null;
    notes.push(
      differs_from_selected
        ? `shadow_visible=true · differs=true · suggested=${nd_recommended_model_id} (advisory only)`
        : `shadow_visible=true · differs=false · ND agrees with selected (still not authority)`,
    );
    if (confidence !== null) {
      notes.push(`confidence=${confidence}`);
    }
  }

  notes.push("live_router_authorized=false");
  notes.push("production_router_verdict=REJECT");

  return {
    selected_model_id,
    nd_recommended_model_id,
    shadow_visible,
    differs_from_selected,
    suggested_model_id,
    confidence,
    task,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    notes,
    authority: "notdiamond_shadow_advisory_only",
  };
}

export function formatNotDiamondShadowAdvisorySummary(
  c: NotDiamondShadowAdvisoryCompose,
): string {
  return (
    `shadow_visible=${c.shadow_visible} · differs=${c.differs_from_selected} · ` +
    `verdict=${c.production_router_verdict} · live_router_authorized=false`
  );
}
