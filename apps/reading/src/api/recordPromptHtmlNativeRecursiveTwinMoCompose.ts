/**
 * Workstation record→prompt model decision + HTML-native recursive twin MO (pure).
 *
 * Operator vision: recorded insights/questions recursively inform prompts with
 * model choice + budget projection, while the HTML-native recursive twin MO
 * write pack remains ready — never injects prompts, never persists records,
 * never PDF primary.
 *
 * record_persisted / prompts_injected always false.
 * pdf_view_authorized / pdf_primary always false.
 * twin_written / charge_executed always false.
 * production_router_verdict always REJECT; live_router_authorized always false.
 */

import {
  composeWorkstationRecordPromptModelDecision,
  type WorkstationRecordPromptModelDecisionCompose,
  type WorkstationRecordPromptModelDecisionInput,
} from "./workstationRecordPromptModelDecisionCompose";
import {
  composeHtmlNativeRecursiveTwinMoWritePack,
  type HtmlNativeRecursiveTwinMoWritePackCompose,
  type HtmlNativeRecursiveTwinMoWritePackInput,
} from "./htmlNativeRecursiveTwinMoWritePackCompose";

export interface RecordPromptHtmlNativeRecursiveTwinMoInput {
  record_prompt: Omit<
    WorkstationRecordPromptModelDecisionInput,
    "operator_ack"
  >;
  html_pack: Omit<HtmlNativeRecursiveTwinMoWritePackInput, "operator_ack">;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface RecordPromptHtmlNativeRecursiveTwinMoCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  record_prompt: WorkstationRecordPromptModelDecisionCompose;
  html_pack: HtmlNativeRecursiveTwinMoWritePackCompose;
  pack_ready: boolean;
  record_persisted: false;
  prompts_injected: false;
  live_router_authorized: false;
  secrets_stored: false;
  live_meter_read: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  twin_written: false;
  charge_executed: false;
  live_execution_authorized: false;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  inventory_mutated: false;
  live_dispatched: false;
  pack_dispatched: false;
  backlog_mutated: false;
  store_mutated: false;
  production_router_verdict: "REJECT";
  purchase_executed: false;
  notes: string[];
  authority: "record_prompt_html_native_recursive_twin_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Record→prompt model decision overlay on HTML-native recursive twin MO pack.
 * Never injects prompts; never persists records; never PDF primary.
 */
export function composeRecordPromptHtmlNativeRecursiveTwinMo(
  input: RecordPromptHtmlNativeRecursiveTwinMoInput,
): RecordPromptHtmlNativeRecursiveTwinMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.record_prompt || typeof input.record_prompt !== "object") {
    throw new Error("record_prompt must be an object");
  }
  if (!input.html_pack || typeof input.html_pack !== "object") {
    throw new Error("html_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "record_persisted=false · prompts_injected=false · live_router_authorized=false",
    "pdf_view_authorized=false · pdf_primary=false",
    "twin_written=false · charge_executed=false",
    "production_router_verdict=REJECT",
  ];

  const record_prompt = composeWorkstationRecordPromptModelDecision({
    ...input.record_prompt,
    operator_ack: input.operator_ack,
  });
  notes.push(...record_prompt.notes.map((n) => `[record_prompt] ${n}`));

  const html_pack = composeHtmlNativeRecursiveTwinMoWritePack({
    ...input.html_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...html_pack.notes.map((n) => `[html_pack] ${n}`));

  const session_id = requireNonEmpty(record_prompt.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    record_prompt.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(html_pack.week_id, "week_id");

  const aligned =
    html_pack.session_id === session_id &&
    html_pack.parent_asset_id === parent_asset_id;
  if (!aligned) {
    notes.push(
      "session/parent mismatch between record_prompt and html_pack — pack_ready blocked",
    );
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      aligned &&
      record_prompt.pack_ready === true &&
      html_pack.pack_ready === true &&
      html_pack.production_router_verdict === "REJECT" &&
      record_prompt.prompts_injected === false &&
      html_pack.pdf_primary === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      aligned &&
      input.operator_ack === true &&
      html_pack.production_router_verdict === "REJECT" &&
      record_prompt.prompts_injected === false &&
      (record_prompt.pack_ready === true || html_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — record→prompt + HTML-native recursive twin MO ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — record_prompt, html_pack, alignment, or operator_ack gate open",
    );
  }

  if (
    record_prompt.record_persisted !== false ||
    record_prompt.prompts_injected !== false ||
    record_prompt.live_router_authorized !== false ||
    record_prompt.secrets_stored !== false ||
    record_prompt.live_meter_read !== false ||
    html_pack.pdf_view_authorized !== false ||
    html_pack.pdf_primary !== false ||
    html_pack.twin_written !== false ||
    html_pack.charge_executed !== false ||
    html_pack.production_router_verdict !== "REJECT" ||
    html_pack.live_router_authorized !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");
  notes.push("live_router_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("live_meter_read=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("twin_written=false");
  notes.push("charge_executed=false");
  notes.push("live_execution_authorized=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("inventory_mutated=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("purchase_executed=false");

  return {
    session_id,
    parent_asset_id,
    week_id,
    record_prompt,
    html_pack,
    pack_ready,
    record_persisted: false,
    prompts_injected: false,
    live_router_authorized: false,
    secrets_stored: false,
    live_meter_read: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    twin_written: false,
    charge_executed: false,
    live_execution_authorized: false,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    inventory_mutated: false,
    live_dispatched: false,
    pack_dispatched: false,
    backlog_mutated: false,
    store_mutated: false,
    production_router_verdict: "REJECT",
    purchase_executed: false,
    notes,
    authority: "record_prompt_html_native_recursive_twin_mo_compose_advisory",
  };
}

export function formatRecordPromptHtmlNativeRecursiveTwinMoSummary(
  c: RecordPromptHtmlNativeRecursiveTwinMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `record_prompt_ready=${c.record_prompt.pack_ready} · ` +
    `html_pack_ready=${c.html_pack.pack_ready} · ` +
    `would_exceed=${c.record_prompt.would_exceed} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `prompts_injected=false · pdf_primary=false · record_persisted=false`
  );
}
