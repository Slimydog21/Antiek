/**
 * Competition-quality deep research + workstation interrogation loop (pure).
 *
 * Operator vision: highest-quality DR product in the world — competition gap
 * awareness, arxiv/substack citations, quality/budget honesty — while living
 * in the research workstation: chase questions, record substrate, inform the
 * next prompt. Pure readiness only.
 *
 * live_dispatch_authorized always false.
 * live_dispatched always false.
 * remote_fetched always false.
 * backlog_mutated always false.
 * record_persisted always false.
 * prompts_injected always false.
 */

import {
  composeCompetitionDrQualitySourcePack,
  type CompetitionDrQualitySourcePackCompose,
} from "./competitionDrQualitySourcePackCompose";
import type {
  CompetitorDecision,
  DecisionArea,
} from "./competitionDeepResearchGap";
import type {
  CitationFamily,
  CitationRecord,
} from "./deepResearchSourceCitationPack";
import {
  composeResearchWorkstationInterrogationLoop,
  type ResearchWorkstationInterrogationLoopCompose,
} from "./researchWorkstationInterrogationLoopCompose";
import type {
  ChaseMode,
  ChaseQuestion,
  SourceFamilyHint,
} from "./researchInterrogationSubagentChaseCompose";
import type { SessionRecordItem } from "./workstationSessionInsightRecordCompose";
import type { ModelOption } from "./modelDecisionPromptCompose";
import type {
  BenchTaskBest,
  NotDiamondShadowRec,
} from "./settingsModelDriverTabCompose";

export interface CompetitionQualityInterrogationLoopInput {
  session_id: string;
  parent_asset_id: string;
  /** Competition + citation + quality/budget. */
  competitor_decisions: CompetitorDecision[];
  focus_areas?: DecisionArea[] | null;
  requested_families: CitationFamily[];
  citations: CitationRecord[];
  filter_to_selected_families?: boolean;
  quality_overall: number | null;
  quality_floor?: number;
  require_no_behind_gaps?: boolean;
  /** Interrogation loop. */
  questions: ChaseQuestion[];
  chase_mode: ChaseMode;
  prior_records?: SessionRecordItem[] | null;
  user_prompt: string;
  selected_model_id: string;
  models: ModelOption[];
  daily_cap_usd: number | null;
  spent_usd: number | null;
  projected_cost_usd_high?: number | null;
  projected_cost_usd_low?: number | null;
  would_exceed: boolean | null;
  operator_override?: boolean;
  source_families?: SourceFamilyHint[] | null;
  bench_bests?: BenchTaskBest[] | null;
  focus_task?: string | null;
  nd_shadow?: NotDiamondShadowRec | null;
  operator_ack: boolean;
}

export interface CompetitionQualityInterrogationLoopCompose {
  session_id: string;
  parent_asset_id: string;
  quality_pack: CompetitionDrQualitySourcePackCompose;
  interrogation: ResearchWorkstationInterrogationLoopCompose;
  /**
   * True when quality_pack.pack_ready and interrogation.loop_ready.
   * Still never live-dispatches.
   */
  session_ready: boolean;
  live_dispatch_authorized: false;
  live_dispatched: false;
  remote_fetched: false;
  backlog_mutated: false;
  record_persisted: false;
  prompts_injected: false;
  notes: string[];
  authority: "competition_quality_interrogation_loop_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose world-class DR quality pack + workstation interrogation loop.
 * Never dispatches, fetches, or persists.
 */
export function composeCompetitionQualityInterrogationLoop(
  input: CompetitionQualityInterrogationLoopInput,
): CompetitionQualityInterrogationLoopCompose {
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
    "live_dispatch_authorized=false — quality+interrogation pure readiness",
    "live_dispatched=false — chase slots intent only",
    "remote_fetched=false — no arxiv/substack network fetch",
    "backlog_mutated=false · record_persisted=false · prompts_injected=false",
  ];

  const quality_pack = composeCompetitionDrQualitySourcePack({
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
  });
  notes.push(...quality_pack.notes.map((n) => `[quality] ${n}`));

  const interrogation = composeResearchWorkstationInterrogationLoop({
    session_id,
    parent_asset_id,
    questions: input.questions,
    chase_mode: input.chase_mode,
    prior_records: input.prior_records,
    user_prompt: input.user_prompt,
    selected_model_id: input.selected_model_id,
    models: input.models,
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
    projected_cost_usd_high: input.projected_cost_usd_high,
    projected_cost_usd_low: input.projected_cost_usd_low,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    source_families: input.source_families,
    bench_bests: input.bench_bests,
    focus_task: input.focus_task ?? "deep_research",
    nd_shadow: input.nd_shadow,
    operator_ack: input.operator_ack,
    mark_for_twin_record: true,
    mark_for_prompt_context: true,
  });
  notes.push(...interrogation.notes.map((n) => `[interrogation] ${n}`));

  const session_ready =
    quality_pack.pack_ready === true &&
    interrogation.loop_ready === true &&
    input.operator_ack === true;

  if (session_ready) {
    notes.push(
      "session_ready=true — competition-quality DR + interrogation loop ready; still pure",
    );
  } else {
    notes.push(
      "session_ready=false — quality pack, interrogation loop, or operator_ack gate open",
    );
  }

  if (
    quality_pack.live_dispatch_authorized !== false ||
    quality_pack.remote_fetched !== false ||
    quality_pack.backlog_mutated !== false ||
    interrogation.live_dispatched !== false ||
    interrogation.record_persisted !== false ||
    interrogation.prompts_injected !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatch_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("remote_fetched=false");
  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");

  return {
    session_id,
    parent_asset_id,
    quality_pack,
    interrogation,
    session_ready,
    live_dispatch_authorized: false,
    live_dispatched: false,
    remote_fetched: false,
    backlog_mutated: false,
    record_persisted: false,
    prompts_injected: false,
    notes,
    authority: "competition_quality_interrogation_loop_compose_advisory",
  };
}

export function formatCompetitionQualityInterrogationLoopSummary(
  c: CompetitionQualityInterrogationLoopCompose,
): string {
  return (
    `session_ready=${c.session_ready} · ` +
    `quality_pack_ready=${c.quality_pack.pack_ready} · ` +
    `loop_ready=${c.interrogation.loop_ready} · ` +
    `chase_slots=${c.interrogation.chase.slot_count} · ` +
    `live_dispatch_authorized=false · remote_fetched=false · record_persisted=false`
  );
}
