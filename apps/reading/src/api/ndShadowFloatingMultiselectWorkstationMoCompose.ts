/**
 * NotDiamond shadow REJECT + floating multi-select workstation marketplace MO (pure).
 *
 * Operator: ND investigated as router — §16 REJECT production. Shadow advisory
 * only next to multi-select collective + workstation marketplace MO pack.
 *
 * production_router_verdict always REJECT.
 * live_router_authorized always false.
 * All multi-select / marketplace honesty flags always false.
 */

import {
  composeNotDiamondShadowAdvisory,
  type NotDiamondShadowAdvisoryCompose,
  type NotDiamondShadowAdvisoryInput,
} from "./notDiamondShadowAdvisoryCompose";
import {
  composeFloatingMultiselectWorkstationMarketplaceMo,
  type FloatingMultiselectWorkstationMarketplaceMoCompose,
  type FloatingMultiselectWorkstationMarketplaceMoInput,
} from "./floatingMultiselectWorkstationMarketplaceMoCompose";

export interface NdShadowFloatingMultiselectWorkstationMoInput {
  nd_shadow: NotDiamondShadowAdvisoryInput;
  research_pack: Omit<
    FloatingMultiselectWorkstationMarketplaceMoInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface NdShadowFloatingMultiselectWorkstationMoCompose {
  session_id: string;
  parent_asset_id: string;
  nd_shadow: NotDiamondShadowAdvisoryCompose;
  research_pack: FloatingMultiselectWorkstationMarketplaceMoCompose;
  pack_ready: boolean;
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  analysis_written: false;
  record_persisted: false;
  prompts_injected: false;
  purchase_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  twin_written: false;
  live_execution_authorized: false;
  store_mutated: false;
  notes: string[];
  authority: "nd_shadow_floating_multiselect_workstation_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose ND shadow advisory with multi-select workstation marketplace MO pack.
 * Never authorizes ND as production router; never live-dispatches.
 */
export function composeNdShadowFloatingMultiselectWorkstationMo(
  input: NdShadowFloatingMultiselectWorkstationMoInput,
): NdShadowFloatingMultiselectWorkstationMoCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.nd_shadow || typeof input.nd_shadow !== "object") {
    throw new Error("nd_shadow must be an object");
  }
  if (!input.research_pack || typeof input.research_pack !== "object") {
    throw new Error("research_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "production_router_verdict=REJECT — NotDiamond not production router (§16)",
    "live_router_authorized=false",
    "live_dispatched=false · pack_dispatched=false · merge_executed=false",
    "record_persisted=false · prompts_injected=false · purchase_executed=false",
    "live_execution_authorized=false · twin_written=false · store_mutated=false",
  ];

  const nd_shadow = composeNotDiamondShadowAdvisory(input.nd_shadow);
  notes.push(...nd_shadow.notes.map((n) => `[nd_shadow] ${n}`));

  if (nd_shadow.production_router_verdict !== "REJECT") {
    throw new Error("invariant: production_router_verdict must be REJECT");
  }
  if (nd_shadow.live_router_authorized !== false) {
    throw new Error("invariant: live_router_authorized must remain false");
  }

  const research_pack = composeFloatingMultiselectWorkstationMarketplaceMo({
    ...input.research_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...research_pack.notes.map((n) => `[research_pack] ${n}`));

  const session_id = requireNonEmpty(research_pack.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    research_pack.parent_asset_id,
    "parent_asset_id",
  );

  // Shadow is advisory; pack_ready does not require shadow_visible
  // (kill switch on is valid production posture).
  let pack_ready = false;
  if (require_both) {
    pack_ready =
      research_pack.pack_ready === true &&
      nd_shadow.live_router_authorized === false &&
      nd_shadow.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      nd_shadow.production_router_verdict === "REJECT" &&
      (research_pack.pack_ready === true || nd_shadow.shadow_visible === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — research pack ready + ND production REJECT held; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — research_pack, ND invariant, or operator_ack gate open",
    );
  }

  if (
    research_pack.live_dispatched !== false ||
    research_pack.live_execution_authorized !== false ||
    research_pack.purchase_executed !== false ||
    research_pack.record_persisted !== false ||
    research_pack.pack_dispatched !== false ||
    research_pack.prompts_injected !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("analysis_written=false");
  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("twin_written=false");
  notes.push("live_execution_authorized=false");
  notes.push("store_mutated=false");

  return {
    session_id,
    parent_asset_id,
    nd_shadow,
    research_pack,
    pack_ready,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    analysis_written: false,
    record_persisted: false,
    prompts_injected: false,
    purchase_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    twin_written: false,
    live_execution_authorized: false,
    store_mutated: false,
    notes,
    authority: "nd_shadow_floating_multiselect_workstation_mo_compose_advisory",
  };
}

export function formatNdShadowFloatingMultiselectWorkstationMoSummary(
  c: NdShadowFloatingMultiselectWorkstationMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `research_ready=${c.research_pack.pack_ready} · ` +
    `shadow_visible=${c.nd_shadow.shadow_visible} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `live_router_authorized=false · live_dispatched=false · ` +
    `purchase_executed=false · live_execution_authorized=false`
  );
}
