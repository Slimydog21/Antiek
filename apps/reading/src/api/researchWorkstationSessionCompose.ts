/**
 * Research workstation session compose (pure).
 *
 * Operator vision: live in the research workstation; chase questions with
 * subagents; record insights/questions; know session readiness before
 * dispatch. Composes caller-supplied gate signals into one session snapshot.
 *
 * live_dispatch_authorized is always false in this pure layer.
 */

export interface ResearchWorkstationSessionInput {
  session_id: string;
  parent_asset_id: string;
  /** Open / completed floating deep-research instance count. */
  floating_instance_count: number;
  /** Twin bind proposed or bound for parent (caller-supplied). */
  twin_bound: boolean;
  /** Source families selected for this session. */
  source_family_count: number;
  /** Quality overall from rubric; null = unknown. */
  quality_overall: number | null;
  quality_floor?: number;
  /** Prompt budget would_exceed; null = unknown honesty. */
  would_exceed: boolean | null;
  /** Cohesive multi-instance pack ready (operator_ack). */
  cohesive_pack_ready?: boolean;
  /** Operator override when budget unknown or would_exceed. */
  operator_override?: boolean;
}

export interface ResearchWorkstationSessionCompose {
  session_id: string;
  parent_asset_id: string;
  floating_instance_count: number;
  twin_bound: boolean;
  sources_ready: boolean;
  quality_ready: boolean;
  budget_ready: boolean;
  floating_ready: boolean;
  twin_ready: boolean;
  cohesive_ready: boolean;
  /** All advisory gates pass. */
  session_ready: boolean;
  /** Always false — pure compose never authorizes live dispatch. */
  live_dispatch_authorized: false;
  notes: string[];
  authority: "research_workstation_session_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function requireNonNegInt(value: unknown, name: string): number {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    value < 0 ||
    !Number.isInteger(value)
  ) {
    throw new Error(`${name} must be a non-negative integer`);
  }
  return value;
}

function requireBool(value: unknown, name: string): boolean {
  if (typeof value !== "boolean") {
    throw new Error(`${name} must be an explicit boolean`);
  }
  return value;
}

/**
 * Compose workstation session readiness from caller-supplied signals.
 * Never live-dispatches.
 */
export function composeResearchWorkstationSession(
  input: ResearchWorkstationSessionInput,
): ResearchWorkstationSessionCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );
  const floating_instance_count = requireNonNegInt(
    input.floating_instance_count,
    "floating_instance_count",
  );
  const source_family_count = requireNonNegInt(
    input.source_family_count,
    "source_family_count",
  );
  const twin_bound = requireBool(input.twin_bound, "twin_bound");

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

  const cohesive_pack_ready =
    input.cohesive_pack_ready === undefined ? false : input.cohesive_pack_ready;
  if (typeof cohesive_pack_ready !== "boolean") {
    throw new Error("cohesive_pack_ready must be boolean when set");
  }

  const floor =
    input.quality_floor === undefined || input.quality_floor === null
      ? 0.5
      : input.quality_floor;
  if (typeof floor !== "number" || !Number.isFinite(floor) || floor < 0 || floor > 1) {
    throw new Error("quality_floor must be finite in [0, 1] when set");
  }

  if (
    input.quality_overall !== null &&
    input.quality_overall !== undefined &&
    (typeof input.quality_overall !== "number" ||
      !Number.isFinite(input.quality_overall) ||
      input.quality_overall < 0 ||
      input.quality_overall > 1)
  ) {
    throw new Error("quality_overall must be null or finite in [0, 1]");
  }
  const quality_overall =
    input.quality_overall === undefined ? null : input.quality_overall;

  const notes: string[] = [
    "live_dispatch_authorized=false — session compose advisory only",
  ];

  const sources_ready = source_family_count >= 1;
  notes.push(
    sources_ready
      ? `sources_ready=true (families=${source_family_count})`
      : "sources_ready=false — need ≥1 knowledge-dense source family",
  );

  let quality_ready = false;
  if (quality_overall === null) {
    notes.push("quality_ready=false — quality_overall unknown (no invent 1.0)");
  } else if (quality_overall >= floor) {
    quality_ready = true;
    notes.push(
      `quality_ready=true (overall=${quality_overall} floor=${floor})`,
    );
  } else {
    notes.push(
      `quality_ready=false (overall=${quality_overall} < floor=${floor})`,
    );
  }

  let budget_ready = false;
  if (would_exceed === null) {
    if (override) {
      budget_ready = true;
      notes.push(
        "budget_ready=true via operator_override with would_exceed=null (honesty)",
      );
    } else {
      notes.push(
        "budget_ready=false — would_exceed unknown without operator_override",
      );
    }
  } else if (would_exceed === true) {
    if (override) {
      budget_ready = true;
      notes.push(
        "budget_ready=true via operator_override with would_exceed=true",
      );
    } else {
      notes.push("budget_ready=false — would_exceed=true");
    }
  } else {
    budget_ready = true;
    notes.push("budget_ready=true (would_exceed=false)");
  }

  const floating_ready = floating_instance_count >= 1;
  notes.push(
    floating_ready
      ? `floating_ready=true (instances=${floating_instance_count})`
      : "floating_ready=false — no floating deep-research instances yet",
  );

  const twin_ready = twin_bound;
  notes.push(
    twin_ready
      ? "twin_ready=true"
      : "twin_ready=false — twin bind not proposed/bound",
  );

  const cohesive_ready = cohesive_pack_ready;
  notes.push(
    cohesive_ready
      ? "cohesive_ready=true"
      : "cohesive_ready=false — multi-select pack not acked (optional until multi-instance)",
  );

  // Core gates: sources + quality + budget. Floating/twin/cohesive enrich notes
  // but floating is required for "chase" workstation posture; twin required for
  // recursive note-taker posture. Cohesive optional unless floating_instance_count>=2.
  let session_ready =
    sources_ready && quality_ready && budget_ready && floating_ready && twin_ready;
  if (floating_instance_count >= 2 && !cohesive_pack_ready) {
    session_ready = false;
    notes.push(
      "session_ready=false — ≥2 floating instances require cohesive_pack_ready",
    );
  } else if (session_ready) {
    notes.push("session_ready=true — advisory gates pass");
  } else {
    notes.push("session_ready=false — one or more core gates failed");
  }
  notes.push("live_dispatch_authorized=false");

  return {
    session_id,
    parent_asset_id,
    floating_instance_count,
    twin_bound,
    sources_ready,
    quality_ready,
    budget_ready,
    floating_ready,
    twin_ready,
    cohesive_ready,
    session_ready,
    live_dispatch_authorized: false,
    notes,
    authority: "research_workstation_session_compose_advisory",
  };
}

export function formatResearchWorkstationSessionSummary(
  s: ResearchWorkstationSessionCompose,
): string {
  return (
    `session ${s.session_id} · ready=${s.session_ready} · ` +
    `float=${s.floating_instance_count} · twin=${s.twin_bound} · ` +
    `live_dispatch_authorized=false`
  );
}
