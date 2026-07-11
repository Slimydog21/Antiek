/**
 * Competition DR quality + source pack compose (pure).
 *
 * Operator vision: highest-quality deep research product in the world —
 * competition gap awareness + arxiv/substack citation pack + quality/budget
 * gate in one pure readiness pack. Never live-dispatches; never scrapes.
 *
 * live_dispatch_authorized always false.
 * remote_fetched always false.
 * backlog_mutated always false.
 */

import {
  buildCompetitionDeepResearchGap,
  type CompetitionGapMatrix,
  type CompetitorDecision,
  type DecisionArea,
} from "./competitionDeepResearchGap";
import {
  buildDeepResearchSourceCitationPack,
  type CitationFamily,
  type CitationRecord,
  type DeepResearchSourceCitationPack,
} from "./deepResearchSourceCitationPack";
import {
  composeDeepResearchQualityBudgetGate,
  type DeepResearchQualityBudgetGateCompose,
} from "./deepResearchQualityBudgetGateCompose";

export interface CompetitionDrQualitySourcePackInput {
  session_id: string;
  /** Caller-supplied competitor decision records only. */
  competitor_decisions: CompetitorDecision[];
  focus_areas?: DecisionArea[] | null;
  requested_families: CitationFamily[];
  citations: CitationRecord[];
  filter_to_selected_families?: boolean;
  quality_overall: number | null;
  quality_floor?: number;
  would_exceed: boolean | null;
  operator_override?: boolean;
  operator_ack: boolean;
  /**
   * When true, competition "behind" residuals must be empty (or operator
   * override) for pack_ready. Default false — advisory only.
   */
  require_no_behind_gaps?: boolean;
}

export interface CompetitionDrQualitySourcePackCompose {
  session_id: string;
  competition: CompetitionGapMatrix;
  citations: DeepResearchSourceCitationPack;
  quality_budget: DeepResearchQualityBudgetGateCompose;
  /**
   * True when quality_budget.gate_ready and citations.pack_ready and
   * (optional) no behind gaps when require_no_behind_gaps.
   * Still never live-dispatches.
   */
  pack_ready: boolean;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  notes: string[];
  authority: "competition_dr_quality_source_pack_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose competition awareness + citation pack + quality/budget gate.
 * Never dispatches, fetches, or mutates backlog.
 */
export function composeCompetitionDrQualitySourcePack(
  input: CompetitionDrQualitySourcePackInput,
): CompetitionDrQualitySourcePackCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const require_no_behind =
    input.require_no_behind_gaps === undefined
      ? false
      : input.require_no_behind_gaps;
  if (typeof require_no_behind !== "boolean") {
    throw new Error("require_no_behind_gaps must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatch_authorized=false — world-class DR pack is pure readiness",
    "remote_fetched=false — no arxiv/substack network fetch",
    "backlog_mutated=false — competition residuals advisory only",
  ];

  const competition = buildCompetitionDeepResearchGap({
    decisions: input.competitor_decisions,
    focus_areas: input.focus_areas ?? undefined,
  });
  notes.push(...competition.notes);
  notes.push(
    `competition behind=${competition.behind_count} · parity=${competition.parity_count} · ahead=${competition.ahead_count}`,
  );

  const citations = buildDeepResearchSourceCitationPack({
    session_id,
    requested_families: input.requested_families,
    citations: input.citations,
    filter_to_selected_families: input.filter_to_selected_families,
  });
  notes.push(...citations.notes);

  const quality_budget = composeDeepResearchQualityBudgetGate({
    session_id,
    quality_overall: input.quality_overall,
    quality_floor: input.quality_floor,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    citation_pack_ready: citations.pack_ready,
    operator_ack: input.operator_ack,
  });
  notes.push(...quality_budget.notes);

  let competition_ok = true;
  if (require_no_behind && competition.behind_count > 0) {
    competition_ok = false;
    notes.push(
      `competition_ok=false — behind_count=${competition.behind_count} and require_no_behind_gaps=true`,
    );
  } else if (competition.behind_count > 0) {
    notes.push(
      `competition_ok=true (advisory) — behind_count=${competition.behind_count} recorded as residuals, not blocking`,
    );
  } else {
    notes.push("competition_ok=true — no behind residuals in matrix");
  }

  const pack_ready =
    quality_budget.gate_ready &&
    citations.pack_ready &&
    competition_ok &&
    quality_budget.live_dispatch_authorized === false;

  if (!citations.pack_ready) {
    notes.push("pack_ready=false — citation pack not ready");
  } else if (!quality_budget.gate_ready) {
    notes.push("pack_ready=false — quality/budget gate not ready");
  } else if (!competition_ok) {
    notes.push("pack_ready=false — competition behind residuals block");
  } else {
    notes.push(
      "pack_ready=true — competition+sources+quality/budget intent; still live_dispatch_authorized=false",
    );
  }

  if (
    competition.backlog_mutated !== false ||
    citations.remote_fetched !== false ||
    quality_budget.live_dispatch_authorized !== false
  ) {
    throw new Error("invariant: nested honesty flags must remain false");
  }

  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");

  return {
    session_id,
    competition,
    citations,
    quality_budget,
    pack_ready,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    notes,
    authority: "competition_dr_quality_source_pack_compose_advisory",
  };
}

export function formatCompetitionDrQualitySourcePackSummary(
  c: CompetitionDrQualitySourcePackCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · citations=${c.citations.citation_count} · ` +
    `behind=${c.competition.behind_count} · gate=${c.quality_budget.gate_ready} · ` +
    `live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false`
  );
}
