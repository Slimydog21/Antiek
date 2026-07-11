/**
 * Research wrestle session super-compose (pure).
 *
 * Operator vision: live in the research workstation; Interrogate, assess,
 * and wrestle with information; spin floating deep researches; record twin
 * insights/questions; attach source packs; stay budget-honest.
 *
 * Composes caller-supplied signals into one wrestle-session snapshot.
 * live_dispatch_authorized is always false.
 */

export interface ResearchWrestleSessionInput {
  session_id: string;
  parent_asset_id: string;
  /** Open or completed floating deep-research instances. */
  floating_instance_count: number;
  /** Completed floating instances available for merge/analysis. */
  completed_floating_count: number;
  /** Twin insights recorded for parent (caller-supplied count). */
  twin_insight_count: number;
  /** Twin questions recorded for parent (caller-supplied count). */
  twin_question_count: number;
  /** Operator open questions in the wrestle loop (caller-supplied). */
  open_question_count: number;
  /** Source families selected (arxiv/substack/etc registry count). */
  source_family_count: number;
  /** Citation pack ready (caller-supplied advisory). */
  citation_pack_ready: boolean;
  /** Quality overall 0..1 or null unknown. */
  quality_overall: number | null;
  quality_floor?: number;
  /** Budget would_exceed; null = unknown honesty. */
  would_exceed: boolean | null;
  /** Preferred view mode for floating work. */
  preferred_view_mode?: "floating" | "fullscreen" | null;
  /** Operator override when budget unknown or would_exceed. */
  operator_override?: boolean;
}

export interface ResearchWrestleSessionSupercompose {
  session_id: string;
  parent_asset_id: string;
  floating_ready: boolean;
  twin_ready: boolean;
  questions_active: boolean;
  sources_ready: boolean;
  citation_ready: boolean;
  quality_ready: boolean;
  budget_ready: boolean;
  preferred_view_mode: "floating" | "fullscreen" | null;
  /**
   * True when enough substrate exists to continue interrogation/wrestling
   * (floating or twin/questions + sources + quality + budget gates).
   * Never authorizes live dispatch.
   */
  wrestle_ready: boolean;
  /** Always false — pure super-compose never dispatches subagents. */
  live_dispatch_authorized: false;
  notes: string[];
  authority: "research_wrestle_session_supercompose_advisory";
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
 * Super-compose research wrestle session readiness from caller signals.
 * Never live-dispatches.
 */
export function composeResearchWrestleSession(
  input: ResearchWrestleSessionInput,
): ResearchWrestleSessionSupercompose {
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
  const completed_floating_count = requireNonNegInt(
    input.completed_floating_count,
    "completed_floating_count",
  );
  if (completed_floating_count > floating_instance_count) {
    throw new Error(
      "completed_floating_count cannot exceed floating_instance_count",
    );
  }
  const twin_insight_count = requireNonNegInt(
    input.twin_insight_count,
    "twin_insight_count",
  );
  const twin_question_count = requireNonNegInt(
    input.twin_question_count,
    "twin_question_count",
  );
  const open_question_count = requireNonNegInt(
    input.open_question_count,
    "open_question_count",
  );
  const source_family_count = requireNonNegInt(
    input.source_family_count,
    "source_family_count",
  );
  const citation_pack_ready = requireBool(
    input.citation_pack_ready,
    "citation_pack_ready",
  );

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

  let preferred_view_mode: "floating" | "fullscreen" | null = null;
  if (input.preferred_view_mode != null && input.preferred_view_mode !== undefined) {
    if (
      input.preferred_view_mode !== "floating" &&
      input.preferred_view_mode !== "fullscreen"
    ) {
      throw new Error(
        "preferred_view_mode must be floating|fullscreen|null",
      );
    }
    preferred_view_mode = input.preferred_view_mode;
  }

  const notes: string[] = [
    "live_dispatch_authorized=false — wrestle snapshot is advisory only",
    "counts and findings are caller-supplied only (no invent)",
  ];

  const floating_ready = floating_instance_count >= 1;
  notes.push(
    floating_ready
      ? `floating_ready=true · instances=${floating_instance_count} · completed=${completed_floating_count}`
      : "floating_ready=false — no floating deep research instances",
  );

  const twin_ready = twin_insight_count + twin_question_count >= 1;
  notes.push(
    twin_ready
      ? `twin_ready=true · insights=${twin_insight_count} · questions=${twin_question_count}`
      : "twin_ready=false — no twin insights/questions recorded",
  );

  const questions_active = open_question_count >= 1;
  notes.push(
    questions_active
      ? `questions_active=true · open_questions=${open_question_count}`
      : "questions_active=false — no open wrestle questions",
  );

  const sources_ready = source_family_count >= 1;
  notes.push(
    sources_ready
      ? `sources_ready=true · families=${source_family_count}`
      : "sources_ready=false — no source families selected",
  );

  const citation_ready = citation_pack_ready;
  notes.push(
    citation_ready
      ? "citation_ready=true"
      : "citation_ready=false — citation pack not ready",
  );

  const floor =
    input.quality_floor === undefined || input.quality_floor === null
      ? 0.5
      : input.quality_floor;
  if (typeof floor !== "number" || !Number.isFinite(floor) || floor < 0 || floor > 1) {
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

  // Wrestle loop needs: (floating OR twin/questions) + sources + quality + budget
  const substrate =
    floating_ready || twin_ready || questions_active;
  const wrestle_ready =
    substrate && sources_ready && quality_ready && budget_ready;

  if (wrestle_ready) {
    notes.push(
      "wrestle_ready=true — substrate+sources+quality+budget gates pass",
    );
  } else {
    notes.push(
      "wrestle_ready=false — continue recording insights/questions or fix gates",
    );
  }
  if (preferred_view_mode) {
    notes.push(`preferred_view_mode=${preferred_view_mode}`);
  }
  notes.push("live_dispatch_authorized=false");

  return {
    session_id,
    parent_asset_id,
    floating_ready,
    twin_ready,
    questions_active,
    sources_ready,
    citation_ready,
    quality_ready,
    budget_ready,
    preferred_view_mode,
    wrestle_ready,
    live_dispatch_authorized: false,
    notes,
    authority: "research_wrestle_session_supercompose_advisory",
  };
}

export function formatResearchWrestleSessionSummary(
  s: ResearchWrestleSessionSupercompose,
): string {
  return (
    `wrestle_ready=${s.wrestle_ready} · floating=${s.floating_ready} · ` +
    `twin=${s.twin_ready} · sources=${s.sources_ready} · quality=${s.quality_ready} · ` +
    `budget=${s.budget_ready} · live_dispatch_authorized=false`
  );
}
