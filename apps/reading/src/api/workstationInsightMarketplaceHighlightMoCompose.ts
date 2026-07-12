/**
 * Workstation insight records → marketplace highlight float twin MO (pure).
 *
 * Operator vision: valuable insights/questions recorded while wrestling in
 * the workstation recursively inform prompts and the marketplace book →
 * highlight float → recursive twin MO competition research chain —
 * without persisting records or live dispatch.
 *
 * record_persisted / prompts_injected always false.
 * purchase_executed / hosted / pdf_view_authorized / live_execution always false.
 */

import {
  composeWorkstationSessionInsightRecord,
  type WorkstationSessionInsightRecordCompose,
  type WorkstationSessionInsightRecordInput,
} from "./workstationSessionInsightRecordCompose";
import {
  composeMarketplaceHighlightFloatRecursiveTwinMo,
  type MarketplaceHighlightFloatRecursiveTwinMoCompose,
  type MarketplaceHighlightFloatRecursiveTwinMoInput,
} from "./marketplaceHighlightFloatRecursiveTwinMoCompose";

export interface WorkstationInsightMarketplaceHighlightMoInput {
  records: WorkstationSessionInsightRecordInput;
  marketplace_research: Omit<
    MarketplaceHighlightFloatRecursiveTwinMoInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface WorkstationInsightMarketplaceHighlightMoCompose {
  session_id: string;
  parent_asset_id: string;
  records: WorkstationSessionInsightRecordCompose;
  marketplace_research: MarketplaceHighlightFloatRecursiveTwinMoCompose;
  pack_ready: boolean;
  record_persisted: false;
  prompts_injected: false;
  purchase_executed: false;
  charge_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  live_dispatched: false;
  twin_written: false;
  live_execution_authorized: false;
  store_mutated: false;
  notes: string[];
  authority: "workstation_insight_marketplace_highlight_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose workstation insight records with marketplace highlight MO research pack.
 * Never persists records, injects prompts, purchases, or launches workers.
 */
export function composeWorkstationInsightMarketplaceHighlightMo(
  input: WorkstationInsightMarketplaceHighlightMoInput,
): WorkstationInsightMarketplaceHighlightMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.records || typeof input.records !== "object") {
    throw new Error("records must be an object");
  }
  if (
    !input.marketplace_research ||
    typeof input.marketplace_research !== "object"
  ) {
    throw new Error("marketplace_research must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "record_persisted=false · prompts_injected=false — records inform pack advisory only",
    "purchase_executed=false · hosted=false · pdf_view_authorized=false",
    "live_dispatched=false · twin_written=false · live_execution_authorized=false",
    "store_mutated=false",
  ];

  const records = composeWorkstationSessionInsightRecord({
    ...input.records,
    operator_ack: input.operator_ack,
  });
  notes.push(...records.notes.map((n) => `[records] ${n}`));

  const marketplace_research = composeMarketplaceHighlightFloatRecursiveTwinMo(
    {
      ...input.marketplace_research,
      operator_ack: input.operator_ack,
    },
  );
  notes.push(
    ...marketplace_research.notes.map((n) => `[marketplace_research] ${n}`),
  );

  if (records.mark_for_prompt_context && records.record_ready) {
    notes.push(
      `prompt_context_candidates=${records.record_count} — still prompts_injected=false`,
    );
  }

  const session_id = requireNonEmpty(records.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    records.parent_asset_id,
    "parent_asset_id",
  );

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      records.record_ready === true &&
      marketplace_research.pack_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (records.record_ready === true ||
        marketplace_research.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — workstation records + marketplace highlight MO ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — records, marketplace_research, or operator_ack gate open",
    );
  }

  if (
    records.record_persisted !== false ||
    records.prompts_injected !== false ||
    records.store_mutated !== false ||
    marketplace_research.purchase_executed !== false ||
    marketplace_research.hosted !== false ||
    marketplace_research.pdf_view_authorized !== false ||
    marketplace_research.live_execution_authorized !== false ||
    marketplace_research.twin_written !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");
  notes.push("purchase_executed=false");
  notes.push("charge_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("twin_written=false");
  notes.push("live_execution_authorized=false");
  notes.push("store_mutated=false");

  return {
    session_id,
    parent_asset_id,
    records,
    marketplace_research,
    pack_ready,
    record_persisted: false,
    prompts_injected: false,
    purchase_executed: false,
    charge_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    live_dispatched: false,
    twin_written: false,
    live_execution_authorized: false,
    store_mutated: false,
    notes,
    authority: "workstation_insight_marketplace_highlight_mo_compose_advisory",
  };
}

export function formatWorkstationInsightMarketplaceHighlightMoSummary(
  c: WorkstationInsightMarketplaceHighlightMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `records_ready=${c.records.record_ready} · ` +
    `market_research_ready=${c.marketplace_research.pack_ready} · ` +
    `record_count=${c.records.record_count} · ` +
    `record_persisted=false · prompts_injected=false · ` +
    `purchase_executed=false · live_execution_authorized=false`
  );
}
