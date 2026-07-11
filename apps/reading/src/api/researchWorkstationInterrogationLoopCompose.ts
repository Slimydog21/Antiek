/**
 * Research workstation interrogation loop compose (pure).
 *
 * Operator vision: live in the research workstation — interrogate material,
 * send subagents to chase questions, record insights/questions recursively,
 * and feed that substrate into the next prompt + model decision (with budget
 * projection). Pure intent only — never live-dispatches or injects prompts.
 *
 * live_dispatched always false.
 * pack_dispatched always false.
 * record_persisted always false.
 * prompts_injected always false.
 * live_router_authorized always false.
 */

import {
  composeResearchInterrogationSubagentChase,
  type ChaseMode,
  type ChaseQuestion,
  type ResearchInterrogationSubagentChaseCompose,
  type SourceFamilyHint,
} from "./researchInterrogationSubagentChaseCompose";
import {
  composeWorkstationRecordPromptModelDecision,
  type WorkstationRecordPromptModelDecisionCompose,
} from "./workstationRecordPromptModelDecisionCompose";
import type { SessionRecordItem } from "./workstationSessionInsightRecordCompose";
import type { ModelOption } from "./modelDecisionPromptCompose";
import type {
  BenchTaskBest,
  NotDiamondShadowRec,
} from "./settingsModelDriverTabCompose";

export interface ResearchWorkstationInterrogationLoopInput {
  session_id: string;
  parent_asset_id: string;
  /** Questions operator is wrestling with — caller-supplied only. */
  questions: ChaseQuestion[];
  chase_mode: ChaseMode;
  /** Optional prior insights/claims (caller-supplied). */
  prior_records?: SessionRecordItem[] | null;
  user_prompt: string;
  selected_model_id: string;
  models: ModelOption[];
  daily_cap_usd: number | null;
  spent_usd: number | null;
  projected_cost_usd_high?: number | null;
  projected_cost_usd_low?: number | null;
  would_exceed?: boolean | null;
  operator_override?: boolean;
  source_families?: SourceFamilyHint[] | null;
  bench_bests?: BenchTaskBest[] | null;
  focus_task?: string | null;
  nd_shadow?: NotDiamondShadowRec | null;
  operator_ack: boolean;
  /** Default true — mark chase + records for twin/prompt substrate. */
  mark_for_twin_record?: boolean;
  mark_for_prompt_context?: boolean;
}

export interface ResearchWorkstationInterrogationLoopCompose {
  session_id: string;
  parent_asset_id: string;
  chase: ResearchInterrogationSubagentChaseCompose;
  prompt_pack: WorkstationRecordPromptModelDecisionCompose;
  /**
   * True when chase.chase_ready and prompt_pack.pack_ready.
   * Still never dispatches or injects.
   */
  loop_ready: boolean;
  live_dispatched: false;
  pack_dispatched: false;
  record_persisted: false;
  prompts_injected: false;
  live_router_authorized: false;
  notes: string[];
  authority: "research_workstation_interrogation_loop_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Build session records from chase questions + prior records.
 * Never invents insight bodies beyond caller-supplied question text.
 */
function buildLoopRecords(
  questions: ChaseQuestion[],
  prior: SessionRecordItem[] | null | undefined,
): SessionRecordItem[] {
  const records: SessionRecordItem[] = [];
  if (prior != null) {
    if (!Array.isArray(prior)) {
      throw new Error("prior_records must be an array when set");
    }
    for (const r of prior) {
      records.push(r);
    }
  }
  for (const q of questions) {
    records.push({
      record_id: `q-${q.question_id}`,
      kind: "question",
      body: q.body,
      source_ref: q.question_id,
    });
  }
  if (records.length === 0) {
    throw new Error("loop requires ≥1 question or prior record");
  }
  return records;
}

/**
 * Compose interrogation chase → session records → prompt/model decision.
 * Never live-dispatches chases; never persists; never injects prompts.
 */
export function composeResearchWorkstationInterrogationLoop(
  input: ResearchWorkstationInterrogationLoopInput,
): ResearchWorkstationInterrogationLoopCompose {
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
  if (!Array.isArray(input.questions) || input.questions.length === 0) {
    throw new Error("questions must be a non-empty array");
  }

  const notes: string[] = [
    "live_dispatched=false — chase slots are pure intent",
    "pack_dispatched=false",
    "record_persisted=false — session substrate advisory only",
    "prompts_injected=false — proposed prompt envelope only",
    "live_router_authorized=false — operator selects model",
  ];

  const mark_for_twin =
    input.mark_for_twin_record === undefined
      ? true
      : input.mark_for_twin_record;
  if (typeof mark_for_twin !== "boolean") {
    throw new Error("mark_for_twin_record must be boolean when set");
  }

  // Budget honesty for chase: prefer explicit would_exceed; else null
  const would_exceed =
    input.would_exceed === undefined ? null : input.would_exceed;
  if (
    would_exceed !== null &&
    would_exceed !== undefined &&
    typeof would_exceed !== "boolean"
  ) {
    throw new Error("would_exceed must be boolean or null");
  }

  const chase = composeResearchInterrogationSubagentChase({
    session_id,
    parent_asset_id,
    questions: input.questions,
    chase_mode: input.chase_mode,
    would_exceed,
    operator_override: input.operator_override,
    selected_model_id: input.selected_model_id,
    source_families: input.source_families,
    operator_ack: input.operator_ack,
    mark_for_twin_record: mark_for_twin,
  });
  notes.push(...chase.notes.map((n) => `[chase] ${n}`));

  const records = buildLoopRecords(input.questions, input.prior_records);
  notes.push(
    `session_records=${records.length} from questions+prior (caller-supplied only)`,
  );

  const prompt_pack = composeWorkstationRecordPromptModelDecision({
    session_id,
    parent_asset_id,
    records,
    user_prompt: input.user_prompt,
    selected_model_id: input.selected_model_id,
    models: input.models,
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
    projected_cost_usd_high: input.projected_cost_usd_high,
    projected_cost_usd_low: input.projected_cost_usd_low,
    bench_bests: input.bench_bests,
    focus_task: input.focus_task ?? "deep_research",
    nd_shadow: input.nd_shadow,
    operator_ack: input.operator_ack,
  });
  notes.push(...prompt_pack.notes.map((n) => `[prompt] ${n}`));

  const loop_ready =
    chase.chase_ready === true &&
    prompt_pack.pack_ready === true &&
    input.operator_ack === true;

  if (loop_ready) {
    notes.push(
      "loop_ready=true — interrogate→chase→record→prompt pack ready; still pure",
    );
  } else {
    notes.push(
      "loop_ready=false — chase, prompt pack, or operator_ack gate open",
    );
  }

  if (
    chase.live_dispatched !== false ||
    chase.pack_dispatched !== false ||
    chase.record_persisted !== false ||
    chase.prompts_injected !== false ||
    prompt_pack.record_persisted !== false ||
    prompt_pack.prompts_injected !== false ||
    prompt_pack.live_router_authorized !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatched=false");
  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");
  notes.push("live_router_authorized=false");

  return {
    session_id,
    parent_asset_id,
    chase,
    prompt_pack,
    loop_ready,
    live_dispatched: false,
    pack_dispatched: false,
    record_persisted: false,
    prompts_injected: false,
    live_router_authorized: false,
    notes,
    authority: "research_workstation_interrogation_loop_compose_advisory",
  };
}

export function formatResearchWorkstationInterrogationLoopSummary(
  c: ResearchWorkstationInterrogationLoopCompose,
): string {
  return (
    `loop_ready=${c.loop_ready} · chase_slots=${c.chase.slot_count} · ` +
    `would_exceed=${c.prompt_pack.would_exceed} · ` +
    `live_dispatched=false · record_persisted=false · prompts_injected=false`
  );
}
