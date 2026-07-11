/**
 * Workstation record pack → prompt context bridge (pure).
 *
 * Operator vision: records of insights/questions recursively inform all
 * prompts. This pure layer bridges a recursive record pack into a proposed
 * prompt envelope + optional model/budget decision snapshot.
 *
 * prompts_injected always false — never mutates live prompt pipelines.
 * record_persisted always false — never writes records.
 */

import {
  composeWorkstationRecursiveRecordPack,
  type WorkstationRecordItem,
  type WorkstationRecursiveRecordPack,
} from "./workstationRecursiveRecordPack";
import {
  composeModelDecisionWithProjection,
  type ModelDecisionPromptComposeResult,
  type ModelOption,
} from "./modelDecisionPromptCompose";

export type ContextPlacement = "prefix" | "suffix";

export interface WorkstationRecordPromptContextBridgeInput {
  session_id: string;
  /** User-facing prompt body (caller-supplied). */
  user_prompt: string;
  /** Record items to pack; required unless prebuilt_pack is supplied. */
  items?: WorkstationRecordItem[] | null;
  /**
   * Optional prebuilt pack (e.g. from prior compose). When set, items may be
   * omitted; pack must already be caller-supplied (not invented).
   */
  prebuilt_pack?: WorkstationRecursiveRecordPack | null;
  max_context_lines?: number | null;
  placement?: ContextPlacement;
  /** Optional model decision for budget projection of the enriched prompt. */
  model_decision?: {
    selected_model_id: string;
    models: ModelOption[];
    daily_cap_usd: number | null;
    spent_usd: number | null;
    projected_cost_usd_high?: number | null;
    projected_cost_usd_low?: number | null;
  } | null;
}

export interface PromptContextEnvelope {
  session_id: string;
  user_prompt: string;
  context_block: string;
  /** Full proposed prompt: context + user (order by placement). */
  proposed_prompt: string;
  context_line_count: number;
  placement: ContextPlacement;
  pack: WorkstationRecursiveRecordPack;
  /** Optional model/budget compose when requested. */
  model_decision: ModelDecisionPromptComposeResult | null;
  bridge_ready: boolean;
  /** Always false — pure bridge never injects into live prompts. */
  prompts_injected: false;
  /** Always false — pure bridge never persists records. */
  record_persisted: false;
  notes: string[];
  authority: "workstation_record_prompt_context_bridge_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function buildContextBlock(lines: string[]): string {
  if (lines.length === 0) return "";
  return (
    "### Workstation recursive context (advisory; caller-supplied only)\n" +
    lines.map((l) => `- ${l}`).join("\n")
  );
}

/**
 * Bridge workstation records into a proposed prompt envelope.
 * Never injects live; never invents record content.
 */
export function bridgeWorkstationRecordPromptContext(
  input: WorkstationRecordPromptContextBridgeInput,
): PromptContextEnvelope {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const user_prompt = requireNonEmpty(input.user_prompt, "user_prompt");

  const placement: ContextPlacement =
    input.placement === undefined || input.placement === null
      ? "prefix"
      : input.placement;
  if (placement !== "prefix" && placement !== "suffix") {
    throw new Error("placement must be prefix|suffix");
  }

  const notes: string[] = [
    "prompts_injected=false — proposed envelope only; no live injection",
    "record_persisted=false — bridge does not write records",
    "context lines are caller-supplied only (no invent)",
  ];

  let pack: WorkstationRecursiveRecordPack;
  if (input.prebuilt_pack != null) {
    const p = input.prebuilt_pack;
    if (!p || typeof p !== "object") {
      throw new Error("prebuilt_pack must be an object when set");
    }
    if (p.record_persisted !== false) {
      throw new Error("prebuilt_pack.record_persisted must be false");
    }
    if (p.prompts_injected !== false) {
      throw new Error("prebuilt_pack.prompts_injected must be false");
    }
    if (!Array.isArray(p.prompt_context_lines)) {
      throw new Error("prebuilt_pack.prompt_context_lines must be an array");
    }
    if (typeof p.session_id !== "string" || !p.session_id.trim()) {
      throw new Error("prebuilt_pack.session_id must be a non-empty string");
    }
    pack = p;
    notes.push("using prebuilt_pack (caller-supplied)");
  } else {
    if (!Array.isArray(input.items)) {
      throw new Error("items must be an array when prebuilt_pack is not set");
    }
    pack = composeWorkstationRecursiveRecordPack({
      session_id,
      items: input.items,
      max_context_lines: input.max_context_lines ?? null,
    });
    notes.push(...pack.notes);
  }

  const context_block = buildContextBlock(pack.prompt_context_lines);
  const proposed_prompt =
    context_block.length === 0
      ? user_prompt
      : placement === "prefix"
        ? `${context_block}\n\n### User prompt\n${user_prompt}`
        : `### User prompt\n${user_prompt}\n\n${context_block}`;

  if (context_block.length === 0) {
    notes.push(
      "context_block empty — proposed_prompt is user_prompt only (no invent context)",
    );
  } else {
    notes.push(
      `context_lines=${pack.prompt_context_lines.length} placement=${placement}`,
    );
  }

  let model_decision: ModelDecisionPromptComposeResult | null = null;
  if (input.model_decision != null) {
    if (typeof input.model_decision !== "object") {
      throw new Error("model_decision must be an object when set");
    }
    model_decision = composeModelDecisionWithProjection({
      selected_model_id: input.model_decision.selected_model_id,
      models: input.model_decision.models,
      daily_cap_usd: input.model_decision.daily_cap_usd,
      spent_usd: input.model_decision.spent_usd,
      projected_cost_usd_high: input.model_decision.projected_cost_usd_high,
      projected_cost_usd_low: input.model_decision.projected_cost_usd_low,
    });
    notes.push(...model_decision.notes);
    notes.push(
      `model_decision attached for selected=${model_decision.selected_model_id}`,
    );
  }

  const bridge_ready =
    user_prompt.length > 0 &&
    (pack.pack_ready || pack.prompt_context_lines.length === 0);
  // Bridge is ready with empty pack (user prompt alone) or with pack_ready.
  notes.push(
    bridge_ready
      ? "bridge_ready=true — proposed envelope prepared (not injected)"
      : "bridge_ready=false",
  );
  notes.push("prompts_injected=false");
  notes.push("record_persisted=false");

  return {
    session_id,
    user_prompt,
    context_block,
    proposed_prompt,
    context_line_count: pack.prompt_context_lines.length,
    placement,
    pack,
    model_decision,
    bridge_ready,
    prompts_injected: false,
    record_persisted: false,
    notes,
    authority: "workstation_record_prompt_context_bridge_advisory",
  };
}

export function formatWorkstationRecordPromptContextBridgeSummary(
  e: PromptContextEnvelope,
): string {
  return (
    `prompt bridge · session=${e.session_id} · lines=${e.context_line_count} · ` +
    `ready=${e.bridge_ready} · prompts_injected=false · record_persisted=false`
  );
}
