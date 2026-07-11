/**
 * Deep research quality + budget gate compose (pure).
 *
 * Operator vision: highest-quality DR product — do not launch when quality
 * is below floor or budget would exceed (unless operator override).
 *
 * live_dispatch_authorized always false.
 */

export interface DeepResearchQualityBudgetGateInput {
  session_id: string;
  /** Quality overall 0..1 or null unknown. */
  quality_overall: number | null;
  quality_floor?: number;
  /** Budget would_exceed; null = unknown honesty. */
  would_exceed: boolean | null;
  operator_override?: boolean;
  /** Optional citation pack ready signal. */
  citation_pack_ready?: boolean;
  operator_ack: boolean;
}

export interface DeepResearchQualityBudgetGateCompose {
  session_id: string;
  quality_ready: boolean;
  budget_ready: boolean;
  citation_ready: boolean;
  /**
   * True when quality_ready + budget_ready (+ citation if provided) and
   * operator_ack. Still never authorizes live dispatch.
   */
  gate_ready: boolean;
  /** Always false — pure gate never authorizes live DR dispatch. */
  live_dispatch_authorized: false;
  notes: string[];
  authority: "deep_research_quality_budget_gate_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose quality + budget launch gate for deep research.
 * Never live-dispatches.
 */
export function composeDeepResearchQualityBudgetGate(
  input: DeepResearchQualityBudgetGateInput,
): DeepResearchQualityBudgetGateCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");

  if (
    input.would_exceed !== null &&
    input.would_exceed !== undefined &&
    typeof input.would_exceed !== "boolean"
  ) {
    throw new Error("would_exceed must be boolean or null");
  }
  const would_exceed =
    input.would_exceed === undefined ? null : input.would_exceed;

  const override =
    input.operator_override === undefined ? false : input.operator_override;
  if (typeof override !== "boolean") {
    throw new Error("operator_override must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatch_authorized=false — quality/budget gate is advisory only",
  ];

  const floor =
    input.quality_floor === undefined || input.quality_floor === null
      ? 0.5
      : input.quality_floor;
  if (
    typeof floor !== "number" ||
    !Number.isFinite(floor) ||
    floor < 0 ||
    floor > 1
  ) {
    throw new Error("quality_floor must be a finite number in [0,1]");
  }

  let quality_ready = false;
  if (input.quality_overall === null || input.quality_overall === undefined) {
    notes.push("quality_ready=false — quality_overall unknown (null honesty)");
  } else if (
    typeof input.quality_overall !== "number" ||
    !Number.isFinite(input.quality_overall)
  ) {
    throw new Error("quality_overall must be number or null");
  } else if (input.quality_overall < 0 || input.quality_overall > 1) {
    throw new Error("quality_overall must be in [0,1]");
  } else {
    quality_ready = input.quality_overall >= floor;
    notes.push(
      quality_ready
        ? `quality_ready=true · overall=${input.quality_overall} floor=${floor}`
        : `quality_ready=false · overall=${input.quality_overall} < floor=${floor}`,
    );
  }

  let budget_ready = false;
  if (would_exceed === null) {
    if (override) {
      budget_ready = true;
      notes.push(
        "budget_ready=true via operator_override (would_exceed unknown)",
      );
    } else {
      notes.push(
        "budget_ready=false — would_exceed unknown and no operator_override",
      );
    }
  } else if (would_exceed === true) {
    if (override) {
      budget_ready = true;
      notes.push(
        "budget_ready=true via operator_override despite would_exceed=true",
      );
    } else {
      notes.push("budget_ready=false — would_exceed=true");
    }
  } else {
    budget_ready = true;
    notes.push("budget_ready=true — would_exceed=false");
  }

  let citation_ready = true;
  if (input.citation_pack_ready !== undefined) {
    if (typeof input.citation_pack_ready !== "boolean") {
      throw new Error("citation_pack_ready must be boolean when set");
    }
    citation_ready = input.citation_pack_ready;
    notes.push(
      citation_ready
        ? "citation_ready=true"
        : "citation_ready=false — citation pack not ready",
    );
  }

  const gate_ready =
    input.operator_ack && quality_ready && budget_ready && citation_ready;

  if (!input.operator_ack) {
    notes.push("gate_ready=false — operator_ack required");
  } else if (!gate_ready) {
    notes.push("gate_ready=false — quality/budget/citation gates closed");
  } else {
    notes.push(
      "gate_ready=true — DR may proceed subject to live dispatch authorization elsewhere",
    );
  }

  notes.push("live_dispatch_authorized=false");

  return {
    session_id,
    quality_ready,
    budget_ready,
    citation_ready,
    gate_ready,
    live_dispatch_authorized: false,
    notes,
    authority: "deep_research_quality_budget_gate_compose_advisory",
  };
}

export function formatDeepResearchQualityBudgetGateSummary(
  c: DeepResearchQualityBudgetGateCompose,
): string {
  return (
    `gate_ready=${c.gate_ready} · quality=${c.quality_ready} · ` +
    `budget=${c.budget_ready} · citation=${c.citation_ready} · ` +
    `live_dispatch_authorized=false`
  );
}
