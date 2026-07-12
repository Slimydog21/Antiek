/**
 * Floating multi-select collective → workstation marketplace MO pack (pure).
 *
 * Operator vision: select multiple floating deep-research instances as one
 * cohesive unit, record workstation insights/questions, and fold into
 * marketplace HTML book → highlight float → recursive twin MO competition —
 * without live dispatch, purchase, or prompt injection.
 *
 * live_dispatched / pack_dispatched / merge_executed / analysis_written always false.
 * record_persisted / prompts_injected / purchase_executed / live_execution always false.
 */

import {
  composeFloatingMultiSelectCollectiveCohesive,
  type FloatingMultiSelectCollectiveCohesiveCompose,
  type FloatingMultiSelectCollectiveCohesiveInput,
} from "./floatingMultiSelectCollectiveCohesiveCompose";
import {
  composeWorkstationInsightMarketplaceHighlightMo,
  type WorkstationInsightMarketplaceHighlightMoCompose,
  type WorkstationInsightMarketplaceHighlightMoInput,
} from "./workstationInsightMarketplaceHighlightMoCompose";

export interface FloatingMultiselectWorkstationMarketplaceMoInput {
  multiselect: Omit<FloatingMultiSelectCollectiveCohesiveInput, "operator_ack">;
  workstation_marketplace: Omit<
    WorkstationInsightMarketplaceHighlightMoInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface FloatingMultiselectWorkstationMarketplaceMoCompose {
  session_id: string;
  parent_asset_id: string;
  multiselect: FloatingMultiSelectCollectiveCohesiveCompose;
  workstation_marketplace: WorkstationInsightMarketplaceHighlightMoCompose;
  pack_ready: boolean;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  analysis_written: false;
  record_persisted: false;
  prompts_injected: false;
  purchase_executed: false;
  charge_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  twin_written: false;
  live_execution_authorized: false;
  store_mutated: false;
  notes: string[];
  authority: "floating_multiselect_workstation_marketplace_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose multi-select cohesive pack with workstation insight marketplace MO.
 * Never dispatches, purchases, persists, or injects prompts.
 */
export function composeFloatingMultiselectWorkstationMarketplaceMo(
  input: FloatingMultiselectWorkstationMarketplaceMoInput,
): FloatingMultiselectWorkstationMarketplaceMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.multiselect || typeof input.multiselect !== "object") {
    throw new Error("multiselect must be an object");
  }
  if (
    !input.workstation_marketplace ||
    typeof input.workstation_marketplace !== "object"
  ) {
    throw new Error("workstation_marketplace must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatched=false · pack_dispatched=false · merge_executed=false · analysis_written=false",
    "record_persisted=false · prompts_injected=false",
    "purchase_executed=false · hosted=false · pdf_view_authorized=false",
    "twin_written=false · live_execution_authorized=false · store_mutated=false",
  ];

  const multiselect = composeFloatingMultiSelectCollectiveCohesive({
    ...input.multiselect,
    operator_ack: input.operator_ack,
  });
  notes.push(...multiselect.notes.map((n) => `[multiselect] ${n}`));

  const workstation_marketplace =
    composeWorkstationInsightMarketplaceHighlightMo({
      ...input.workstation_marketplace,
      operator_ack: input.operator_ack,
    });
  notes.push(
    ...workstation_marketplace.notes.map((n) => `[workstation_marketplace] ${n}`),
  );

  const session_id = requireNonEmpty(multiselect.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    multiselect.parent_asset_id,
    "parent_asset_id",
  );

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      multiselect.pack_ready === true &&
      workstation_marketplace.pack_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (multiselect.pack_ready === true ||
        workstation_marketplace.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — multi-select cohesive + workstation marketplace MO ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — multiselect, workstation_marketplace, or operator_ack gate open",
    );
  }

  if (
    multiselect.live_dispatched !== false ||
    multiselect.pack_dispatched !== false ||
    multiselect.merge_executed !== false ||
    multiselect.analysis_written !== false ||
    workstation_marketplace.record_persisted !== false ||
    workstation_marketplace.prompts_injected !== false ||
    workstation_marketplace.purchase_executed !== false ||
    workstation_marketplace.hosted !== false ||
    workstation_marketplace.live_execution_authorized !== false ||
    workstation_marketplace.twin_written !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("analysis_written=false");
  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");
  notes.push("purchase_executed=false");
  notes.push("charge_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("twin_written=false");
  notes.push("live_execution_authorized=false");
  notes.push("store_mutated=false");

  return {
    session_id,
    parent_asset_id,
    multiselect,
    workstation_marketplace,
    pack_ready,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    analysis_written: false,
    record_persisted: false,
    prompts_injected: false,
    purchase_executed: false,
    charge_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    twin_written: false,
    live_execution_authorized: false,
    store_mutated: false,
    notes,
    authority:
      "floating_multiselect_workstation_marketplace_mo_compose_advisory",
  };
}

export function formatFloatingMultiselectWorkstationMarketplaceMoSummary(
  c: FloatingMultiselectWorkstationMarketplaceMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `multiselect_ready=${c.multiselect.pack_ready} · ` +
    `workstation_marketplace_ready=${c.workstation_marketplace.pack_ready} · ` +
    `selected=${c.multiselect.tray.selected_count} · ` +
    `live_dispatched=false · pack_dispatched=false · ` +
    `record_persisted=false · purchase_executed=false · live_execution_authorized=false`
  );
}
