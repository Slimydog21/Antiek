/**
 * Research launch readiness gate (pure client).
 *
 * Operator vision: before cascade/deep research launch, confirm sources
 * selected, quality floor known, and budget projection does not invent safety.
 *
 * live_dispatch_authorized is always false in this pure layer.
 */

export interface ResearchLaunchReadinessInput {
  session_id: string;
  /** Number of knowledge-dense source families selected (>=1 required). */
  source_family_count: number;
  /** Optional overall quality score from rubric; null = unknown. */
  quality_overall: number | null;
  /** Minimum quality floor (0..1) when quality is known. */
  quality_floor?: number;
  /** Prompt budget would_exceed from projection; null = unknown. */
  would_exceed: boolean | null;
  /** Operator explicit approval to proceed when would_exceed is null/true. */
  operator_override?: boolean;
}

export interface ResearchLaunchReadinessDecision {
  session_id: string;
  sources_ready: boolean;
  quality_ready: boolean;
  budget_ready: boolean;
  /** True when sources + quality + budget gates pass (advisory readiness). */
  launch_ready: boolean;
  /** Always false — pure gate never authorizes live dispatch. */
  live_dispatch_authorized: false;
  notes: string[];
  authority: "research_launch_readiness_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function finiteUnit(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${name} must be a finite number`);
  }
  if (value < 0 || value > 1) {
    throw new Error(`${name} must be in [0, 1]`);
  }
  return value;
}

/**
 * Evaluate whether a research session is ready to launch (advisory).
 * Never authorizes live dispatch.
 */
export function evaluateResearchLaunchReadiness(
  input: ResearchLaunchReadinessInput,
): ResearchLaunchReadinessDecision {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  if (
    typeof input.source_family_count !== "number" ||
    !Number.isFinite(input.source_family_count) ||
    input.source_family_count < 0 ||
    !Number.isInteger(input.source_family_count)
  ) {
    throw new Error("source_family_count must be a non-negative integer");
  }
  if (
    input.would_exceed !== null &&
    input.would_exceed !== undefined &&
    typeof input.would_exceed !== "boolean"
  ) {
    throw new Error("would_exceed must be boolean or null");
  }
  const would_exceed =
    input.would_exceed === undefined ? null : input.would_exceed;
  const operator_override =
    input.operator_override === undefined ? false : input.operator_override;
  if (typeof operator_override !== "boolean") {
    throw new Error("operator_override must be an explicit boolean when set");
  }

  const quality_floor =
    input.quality_floor === undefined ? 0.5 : input.quality_floor;
  finiteUnit(quality_floor, "quality_floor");

  if (
    input.quality_overall !== null &&
    input.quality_overall !== undefined
  ) {
    finiteUnit(input.quality_overall, "quality_overall");
  }
  const quality_overall =
    input.quality_overall === undefined ? null : input.quality_overall;

  const notes: string[] = [
    "live_dispatch_authorized=false — pure readiness gate only",
  ];

  const sources_ready = input.source_family_count >= 1;
  if (!sources_ready) {
    notes.push("source_family_count < 1 — sources_ready=false");
  } else {
    notes.push(`sources_ready=true (families=${input.source_family_count})`);
  }

  let quality_ready = false;
  if (quality_overall === null) {
    // Unknown quality: allow readiness without inventing a score, but note it.
    quality_ready = true;
    notes.push(
      "quality_overall unknown — quality_ready=true (no invent floor fail)",
    );
  } else if (quality_overall >= quality_floor) {
    quality_ready = true;
    notes.push(
      `quality_overall=${quality_overall} >= floor=${quality_floor}`,
    );
  } else {
    quality_ready = false;
    notes.push(
      `quality_overall=${quality_overall} < floor=${quality_floor} — quality_ready=false`,
    );
  }

  let budget_ready = false;
  if (would_exceed === true) {
    if (operator_override) {
      budget_ready = true;
      notes.push(
        "would_exceed=true with operator_override — budget_ready=true (still no live dispatch)",
      );
    } else {
      budget_ready = false;
      notes.push("would_exceed=true without override — budget_ready=false");
    }
  } else if (would_exceed === false) {
    budget_ready = true;
    notes.push("would_exceed=false — budget_ready=true");
  } else {
    // null unknown — fail closed unless override (never invent safe)
    if (operator_override) {
      budget_ready = true;
      notes.push(
        "would_exceed=null with operator_override — budget_ready=true (unknown not invented safe)",
      );
    } else {
      budget_ready = false;
      notes.push(
        "would_exceed=null — budget_ready=false (no invent safe budget)",
      );
    }
  }

  const launch_ready = sources_ready && quality_ready && budget_ready;
  notes.push(`launch_ready=${launch_ready}`);
  notes.push("live_dispatch_authorized=false");

  return {
    session_id,
    sources_ready,
    quality_ready,
    budget_ready,
    launch_ready,
    live_dispatch_authorized: false,
    notes,
    authority: "research_launch_readiness_advisory",
  };
}

export function formatLaunchReadinessSummary(
  d: ResearchLaunchReadinessDecision,
): string {
  return (
    `session=${d.session_id} · launch_ready=${d.launch_ready} · ` +
    `live_dispatch_authorized=false`
  );
}
