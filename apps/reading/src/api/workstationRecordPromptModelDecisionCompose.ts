/**
 * Workstation record → prompt context → model decision pack (pure).
 *
 * Operator vision: while wrestling in the research workstation, recorded
 * insights/questions recursively inform prompts; operator chooses model with
 * usage bar + projection of how the enriched prompt affects budget.
 *
 * record_persisted always false.
 * prompts_injected always false.
 * live_router_authorized always false.
 * secrets_stored always false.
 * live_meter_read always false.
 */

import {
  composeWorkstationSessionInsightRecord,
  type SessionRecordItem,
  type WorkstationSessionInsightRecordCompose,
} from "./workstationSessionInsightRecordCompose";
import {
  bridgeWorkstationRecordPromptContext,
  type ContextPlacement,
  type PromptContextEnvelope,
} from "./workstationRecordPromptContextBridge";
import type { WorkstationRecordItem } from "./workstationRecursiveRecordPack";
import {
  composeSettingsDecisionTreeUsageBar,
  type SettingsDecisionTreeUsageBarCompose,
} from "./settingsDecisionTreeUsageBarCompose";
import type { ModelOption } from "./modelDecisionPromptCompose";
import type {
  BenchTaskBest,
  NotDiamondShadowRec,
} from "./settingsModelDriverTabCompose";

export interface WorkstationRecordPromptModelDecisionInput {
  session_id: string;
  parent_asset_id: string;
  records: SessionRecordItem[];
  user_prompt: string;
  placement?: ContextPlacement;
  max_context_lines?: number | null;
  selected_model_id: string;
  models: ModelOption[];
  daily_cap_usd: number | null;
  spent_usd: number | null;
  /**
   * Optional projected cost for the *enriched* prompt. When null, projection
   * honesty stays null (never invent $0).
   */
  projected_cost_usd_high?: number | null;
  projected_cost_usd_low?: number | null;
  bench_bests?: BenchTaskBest[] | null;
  focus_task?: string | null;
  nd_shadow?: NotDiamondShadowRec | null;
  operator_ack: boolean;
}

export interface WorkstationRecordPromptModelDecisionCompose {
  session_id: string;
  parent_asset_id: string;
  records: WorkstationSessionInsightRecordCompose;
  bridge: PromptContextEnvelope;
  decision: SettingsDecisionTreeUsageBarCompose;
  /**
   * True when records.record_ready, bridge.bridge_ready, decision.decision_ready.
   * Still never injects prompts or routes live.
   */
  pack_ready: boolean;
  proposed_prompt: string;
  would_exceed: boolean | null;
  usage_percent: number | null;
  record_persisted: false;
  prompts_injected: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  notes: string[];
  authority: "workstation_record_prompt_model_decision_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function mapSessionToPackItems(
  records: SessionRecordItem[],
): WorkstationRecordItem[] {
  return records.map((r) => {
    let kind: WorkstationRecordItem["kind"];
    switch (r.kind) {
      case "insight":
        kind = "insight";
        break;
      case "question":
        kind = "question";
        break;
      case "data":
      case "claim":
        kind = "finding";
        break;
      default:
        throw new Error(`unsupported session record kind: ${String(r.kind)}`);
    }
    const item: WorkstationRecordItem = {
      record_id: r.record_id,
      kind,
      text: r.body,
    };
    if (r.source_ref) {
      item.asset_id = r.source_ref;
    }
    return item;
  });
}

/**
 * Compose session records → prompt context envelope → model decision usage bar.
 * Never persists, injects, or live-routes.
 */
export function composeWorkstationRecordPromptModelDecision(
  input: WorkstationRecordPromptModelDecisionInput,
): WorkstationRecordPromptModelDecisionCompose {
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
    "record_persisted=false — records are pure pack only",
    "prompts_injected=false — proposed envelope only",
    "live_router_authorized=false — operator selects model",
    "secrets_stored=false",
    "live_meter_read=false",
  ];

  const records = composeWorkstationSessionInsightRecord({
    session_id,
    parent_asset_id,
    records: input.records,
    operator_ack: input.operator_ack,
    mark_for_prompt_context: true,
  });
  notes.push(...records.notes);

  const packItems = mapSessionToPackItems(input.records);
  const bridge = bridgeWorkstationRecordPromptContext({
    session_id,
    user_prompt: input.user_prompt,
    items: packItems,
    max_context_lines: input.max_context_lines,
    placement: input.placement,
    model_decision: {
      selected_model_id: input.selected_model_id,
      models: input.models,
      daily_cap_usd: input.daily_cap_usd,
      spent_usd: input.spent_usd,
      projected_cost_usd_high: input.projected_cost_usd_high,
      projected_cost_usd_low: input.projected_cost_usd_low,
    },
  });
  notes.push(...bridge.notes);

  const decision = composeSettingsDecisionTreeUsageBar({
    selected_model_id: input.selected_model_id,
    models: input.models,
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
    projected_cost_usd_high: input.projected_cost_usd_high,
    projected_cost_usd_low: input.projected_cost_usd_low,
    bench_bests: input.bench_bests,
    focus_task: input.focus_task,
    nd_shadow: input.nd_shadow,
    operator_ack: input.operator_ack,
  });
  notes.push(...decision.notes);

  // Prefer would_exceed from decision bar (same as bridge model_decision if set)
  const would_exceed =
    decision.would_exceed ??
    (bridge.model_decision ? bridge.model_decision.would_exceed : null);

  const pack_ready =
    records.record_ready &&
    bridge.bridge_ready &&
    decision.decision_ready &&
    records.record_persisted === false &&
    bridge.prompts_injected === false &&
    decision.live_router_authorized === false;

  if (!records.record_ready) {
    notes.push("pack_ready=false — session records not ready");
  } else if (!bridge.bridge_ready) {
    notes.push("pack_ready=false — prompt context bridge not ready");
  } else if (!decision.decision_ready) {
    notes.push("pack_ready=false — model decision tree not ready");
  } else {
    notes.push(
      "pack_ready=true — records→prompt→model intent only; still pure",
    );
  }

  if (
    records.record_persisted !== false ||
    records.prompts_injected !== false ||
    bridge.prompts_injected !== false ||
    bridge.record_persisted !== false ||
    decision.live_router_authorized !== false ||
    decision.secrets_stored !== false ||
    decision.live_meter_read !== false
  ) {
    throw new Error("invariant: nested honesty flags must remain false");
  }

  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");

  return {
    session_id,
    parent_asset_id,
    records,
    bridge,
    decision,
    pack_ready,
    proposed_prompt: bridge.proposed_prompt,
    would_exceed,
    usage_percent: decision.usage_percent,
    record_persisted: false,
    prompts_injected: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    notes,
    authority: "workstation_record_prompt_model_decision_compose_advisory",
  };
}

export function formatWorkstationRecordPromptModelDecisionSummary(
  c: WorkstationRecordPromptModelDecisionCompose,
): string {
  const w =
    c.would_exceed === null
      ? "would_exceed=null"
      : `would_exceed=${c.would_exceed}`;
  const pct =
    c.usage_percent === null
      ? "usage%=null"
      : `usage%=${c.usage_percent.toFixed(1)}`;
  return (
    `pack_ready=${c.pack_ready} · records=${c.records.record_count} · ` +
    `model=${c.decision.driver.decision.selected_model_id} · ${pct} · ${w} · ` +
    `record_persisted=false · prompts_injected=false · live_router_authorized=false · ` +
    `secrets_stored=false · live_meter_read=false`
  );
}
