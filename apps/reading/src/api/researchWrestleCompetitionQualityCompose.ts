/**
 * Research wrestle + competition quality supercompose (pure).
 *
 * Operator vision: live in the research workstation wrestling with information
 * while holding the highest-quality deep research bar — competition gaps,
 * arxiv/substack citations, quality/budget honesty — without live dispatch.
 *
 * live_dispatch_authorized always false.
 * remote_fetched always false.
 * backlog_mutated always false.
 */

import {
  composeResearchWrestleSession,
  type ResearchWrestleSessionInput,
  type ResearchWrestleSessionSupercompose,
} from "./researchWrestleSessionSupercompose";
import {
  composeCompetitionDrQualitySourcePack,
  type CompetitionDrQualitySourcePackCompose,
  type CompetitionDrQualitySourcePackInput,
} from "./competitionDrQualitySourcePackCompose";
import type { CompetitorDecision, DecisionArea } from "./competitionDeepResearchGap";
import type { CitationFamily, CitationRecord } from "./deepResearchSourceCitationPack";

export interface ResearchWrestleCompetitionQualityInput {
  session_id: string;
  parent_asset_id: string;
  /** Wrestle substrate signals (caller-supplied counts/flags). */
  floating_instance_count: number;
  completed_floating_count: number;
  twin_insight_count: number;
  twin_question_count: number;
  open_question_count: number;
  preferred_view_mode?: "floating" | "fullscreen" | null;
  /** Competition + citation + quality/budget inputs. */
  competitor_decisions: CompetitorDecision[];
  focus_areas?: DecisionArea[] | null;
  requested_families: CitationFamily[];
  citations: CitationRecord[];
  filter_to_selected_families?: boolean;
  quality_overall: number | null;
  quality_floor?: number;
  would_exceed: boolean | null;
  operator_override?: boolean;
  require_no_behind_gaps?: boolean;
  operator_ack: boolean;
}

export interface ResearchWrestleCompetitionQualityCompose {
  session_id: string;
  parent_asset_id: string;
  wrestle: ResearchWrestleSessionSupercompose;
  competition_quality: CompetitionDrQualitySourcePackCompose;
  /**
   * True when wrestle_ready and competition_quality.pack_ready.
   * Still never live-dispatches.
   */
  session_ready: boolean;
  live_dispatch_authorized: false;
  remote_fetched: false;
  backlog_mutated: false;
  notes: string[];
  authority: "research_wrestle_competition_quality_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Super-compose wrestle session + world-class DR competition/quality pack.
 * Never live-dispatches; never scrapes; never mutates backlog.
 */
export function composeResearchWrestleCompetitionQuality(
  input: ResearchWrestleCompetitionQualityInput,
): ResearchWrestleCompetitionQualityCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );

  const notes: string[] = [
    "live_dispatch_authorized=false — wrestle+quality pack is pure readiness",
    "remote_fetched=false — no arxiv/substack network fetch",
    "backlog_mutated=false — competition residuals advisory only",
  ];

  // Derive source_family_count and citation_pack_ready from competition pack
  // after compose; first pass quality pack, then wrestle with its signals.
  const qualityInput: CompetitionDrQualitySourcePackInput = {
    session_id,
    competitor_decisions: input.competitor_decisions,
    focus_areas: input.focus_areas,
    requested_families: input.requested_families,
    citations: input.citations,
    filter_to_selected_families: input.filter_to_selected_families,
    quality_overall: input.quality_overall,
    quality_floor: input.quality_floor,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    operator_ack: input.operator_ack,
    require_no_behind_gaps: input.require_no_behind_gaps,
  };
  const competition_quality =
    composeCompetitionDrQualitySourcePack(qualityInput);
  notes.push(...competition_quality.notes);

  const familyCount = Array.isArray(
    competition_quality.citations.selection?.families,
  )
    ? competition_quality.citations.selection.families.length
    : Array.isArray(input.requested_families)
      ? input.requested_families.length
      : 0;

  const wrestleInput: ResearchWrestleSessionInput = {
    session_id,
    parent_asset_id,
    floating_instance_count: input.floating_instance_count,
    completed_floating_count: input.completed_floating_count,
    twin_insight_count: input.twin_insight_count,
    twin_question_count: input.twin_question_count,
    open_question_count: input.open_question_count,
    source_family_count: familyCount,
    citation_pack_ready: competition_quality.citations.pack_ready,
    quality_overall: input.quality_overall,
    quality_floor: input.quality_floor,
    would_exceed: input.would_exceed,
    preferred_view_mode: input.preferred_view_mode,
    operator_override: input.operator_override,
  };
  const wrestle = composeResearchWrestleSession(wrestleInput);
  notes.push(...wrestle.notes);

  const session_ready =
    wrestle.wrestle_ready &&
    competition_quality.pack_ready &&
    wrestle.live_dispatch_authorized === false &&
    competition_quality.live_dispatch_authorized === false;

  if (!wrestle.wrestle_ready) {
    notes.push("session_ready=false — wrestle substrate not ready");
  } else if (!competition_quality.pack_ready) {
    notes.push(
      "session_ready=false — competition/quality/source pack not ready",
    );
  } else {
    notes.push(
      "session_ready=true — wrestle+competition quality intent only; still pure",
    );
  }

  if (
    wrestle.live_dispatch_authorized !== false ||
    competition_quality.live_dispatch_authorized !== false ||
    competition_quality.remote_fetched !== false ||
    competition_quality.backlog_mutated !== false
  ) {
    throw new Error("invariant: nested honesty flags must remain false");
  }

  notes.push("live_dispatch_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");

  return {
    session_id,
    parent_asset_id,
    wrestle,
    competition_quality,
    session_ready,
    live_dispatch_authorized: false,
    remote_fetched: false,
    backlog_mutated: false,
    notes,
    authority: "research_wrestle_competition_quality_compose_advisory",
  };
}

export function formatResearchWrestleCompetitionQualitySummary(
  c: ResearchWrestleCompetitionQualityCompose,
): string {
  return (
    `session_ready=${c.session_ready} · wrestle_ready=${c.wrestle.wrestle_ready} · ` +
    `quality_pack_ready=${c.competition_quality.pack_ready} · ` +
    `citations=${c.competition_quality.citations.citation_count} · ` +
    `behind=${c.competition_quality.competition.behind_count} · ` +
    `live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false`
  );
}
