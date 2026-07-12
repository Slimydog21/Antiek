/**
 * Recursive twin note-taker residual over twin intelligent search + model
 * decision budget + HTML-native settings marketplace free competition DR ND
 * pack (pure).
 *
 * Operator vision: every information asset has a twin document of insights and
 * questions (LLM as perfect note-taker). Propose that twin substrate over twin
 * intelligent search + model decision-tree usage bar + HTML-native free-first
 * marketplace honesty — without writing twins, remote-indexing, purchasing,
 * live-routing, or PDF-primary views.
 *
 * twin_written / prompts_injected / live_dispatch_authorized always false.
 * remote_index_queried / live_router_authorized / secrets_stored always false.
 * pdf_primary / purchase_executed / hosted always false.
 * production_router_verdict always REJECT.
 */

import {
  composeRecursiveTwinNoteTaker,
  type RecursiveTwinNoteTakerCompose,
  type RecursiveTwinNoteTakerInput,
} from "./recursiveTwinNoteTakerCompose";
import {
  composeTwinSearchModelDecisionHtmlNativeSettingsMarketplace,
  type TwinSearchModelDecisionHtmlNativeSettingsMarketplaceCompose,
  type TwinSearchModelDecisionHtmlNativeSettingsMarketplaceInput,
} from "./twinSearchModelDecisionHtmlNativeSettingsMarketplaceCompose";

export interface RecursiveTwinNoteTakerTwinSearchModelDecisionInput {
  twin: Omit<RecursiveTwinNoteTakerInput, "operator_ack">;
  twin_search_pack: Omit<
    TwinSearchModelDecisionHtmlNativeSettingsMarketplaceInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require twin.twin_propose_ready AND
   * twin_search_pack.pack_ready, and parent_asset_id alignment.
   */
  require_both?: boolean;
}

export interface RecursiveTwinNoteTakerTwinSearchModelDecisionCompose {
  session_id: string;
  parent_asset_id: string;
  title: string;
  account_id: string;
  week_id: string;
  asset_id: string;
  twin: RecursiveTwinNoteTakerCompose;
  twin_search_pack: TwinSearchModelDecisionHtmlNativeSettingsMarketplaceCompose;
  parent_aligned: boolean;
  pack_ready: boolean;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  purchase_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  remote_fetched: false;
  backlog_mutated: false;
  secrets_stored: false;
  inventory_mutated: false;
  live_router_authorized: false;
  live_meter_read: false;
  suite_rewritten: false;
  store_mutated: false;
  live_execution_authorized: false;
  charge_executed: false;
  remote_index_queried: false;
  live_dispatched: false;
  pack_dispatched: false;
  merge_executed: false;
  draft_written: false;
  record_persisted: false;
  analysis_written: false;
  production_router_verdict: "REJECT";
  notes: string[];
  authority: "recursive_twin_note_taker_twin_search_model_decision_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Recursive twin note-taker stacked on twin search model decision HTML-native pack.
 * Never writes twins; never remote-indexes; ND REJECT.
 */
export function composeRecursiveTwinNoteTakerTwinSearchModelDecision(
  input: RecursiveTwinNoteTakerTwinSearchModelDecisionInput,
): RecursiveTwinNoteTakerTwinSearchModelDecisionCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.twin || typeof input.twin !== "object") {
    throw new Error("twin must be an object");
  }
  if (!input.twin_search_pack || typeof input.twin_search_pack !== "object") {
    throw new Error("twin_search_pack must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "twin_written=false — twin document not created/updated",
    "prompts_injected=false — no live LLM note-taker prompt injection",
    "live_dispatch_authorized=false — no automatic twin agent dispatch",
    "remote_index_queried=false · production_router_verdict=REJECT",
  ];

  const twin = composeRecursiveTwinNoteTaker({
    ...input.twin,
    operator_ack: input.operator_ack,
  });
  notes.push(...twin.notes.map((n) => `[twin] ${n}`));

  const twin_search_pack =
    composeTwinSearchModelDecisionHtmlNativeSettingsMarketplace({
      ...input.twin_search_pack,
      operator_ack: input.operator_ack,
    });
  notes.push(...twin_search_pack.notes.map((n) => `[twin_search_pack] ${n}`));

  const parent_asset_id = requireNonEmpty(
    twin.parent_asset_id,
    "parent_asset_id",
  );
  const session_id = requireNonEmpty(twin_search_pack.session_id, "session_id");
  const title = requireNonEmpty(twin_search_pack.title, "title");
  const account_id = requireNonEmpty(twin_search_pack.account_id, "account_id");
  const week_id = requireNonEmpty(twin_search_pack.week_id, "week_id");
  const asset_id = requireNonEmpty(twin_search_pack.asset_id, "asset_id");

  const search_parent = requireNonEmpty(
    twin_search_pack.parent_asset_id,
    "twin_search_pack.parent_asset_id",
  );
  const parent_aligned = parent_asset_id === search_parent;
  if (!parent_aligned) {
    notes.push(
      `parent_aligned=false — twin.parent=${parent_asset_id} twin_search_pack.parent=${search_parent}`,
    );
  } else {
    notes.push("parent_aligned=true");
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      twin.twin_propose_ready === true &&
      twin_search_pack.pack_ready === true &&
      parent_aligned === true &&
      twin.twin_written === false &&
      twin.prompts_injected === false &&
      twin.live_dispatch_authorized === false &&
      twin_search_pack.remote_index_queried === false &&
      twin_search_pack.twin_written === false &&
      twin_search_pack.purchase_executed === false &&
      twin_search_pack.hosted === false &&
      twin_search_pack.pdf_primary === false &&
      twin_search_pack.pdf_view_authorized === false &&
      twin_search_pack.secrets_stored === false &&
      twin_search_pack.live_router_authorized === false &&
      twin_search_pack.live_meter_read === false &&
      twin_search_pack.inventory_mutated === false &&
      twin_search_pack.suite_rewritten === false &&
      twin_search_pack.charge_executed === false &&
      twin_search_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      twin.twin_written === false &&
      twin.prompts_injected === false &&
      twin.live_dispatch_authorized === false &&
      twin_search_pack.remote_index_queried === false &&
      twin_search_pack.pdf_primary === false &&
      twin_search_pack.production_router_verdict === "REJECT" &&
      (twin.twin_propose_ready === true || twin_search_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — recursive twin note-taker + twin search model decision ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — twin, twin_search_pack, parent align, or operator_ack gate open",
    );
  }

  if (
    twin.twin_written !== false ||
    twin.prompts_injected !== false ||
    twin.live_dispatch_authorized !== false ||
    twin_search_pack.remote_index_queried !== false ||
    twin_search_pack.twin_written !== false ||
    twin_search_pack.purchase_executed !== false ||
    twin_search_pack.hosted !== false ||
    twin_search_pack.pdf_primary !== false ||
    twin_search_pack.pdf_view_authorized !== false ||
    twin_search_pack.secrets_stored !== false ||
    twin_search_pack.live_router_authorized !== false ||
    twin_search_pack.live_meter_read !== false ||
    twin_search_pack.inventory_mutated !== false ||
    twin_search_pack.suite_rewritten !== false ||
    twin_search_pack.charge_executed !== false ||
    twin_search_pack.production_router_verdict !== "REJECT"
  ) {
    throw new Error("invariant: honesty flags must remain false / REJECT");
  }

  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("remote_fetched=false");
  notes.push("backlog_mutated=false");
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_router_authorized=false");
  notes.push("live_meter_read=false");
  notes.push("suite_rewritten=false");
  notes.push("store_mutated=false");
  notes.push("live_execution_authorized=false");
  notes.push("charge_executed=false");
  notes.push("remote_index_queried=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("draft_written=false");
  notes.push("record_persisted=false");
  notes.push("analysis_written=false");
  notes.push("production_router_verdict=REJECT");

  return {
    session_id,
    parent_asset_id,
    title,
    account_id,
    week_id,
    asset_id,
    twin,
    twin_search_pack,
    parent_aligned,
    pack_ready,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    purchase_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    remote_fetched: false,
    backlog_mutated: false,
    secrets_stored: false,
    inventory_mutated: false,
    live_router_authorized: false,
    live_meter_read: false,
    suite_rewritten: false,
    store_mutated: false,
    live_execution_authorized: false,
    charge_executed: false,
    remote_index_queried: false,
    live_dispatched: false,
    pack_dispatched: false,
    merge_executed: false,
    draft_written: false,
    record_persisted: false,
    analysis_written: false,
    production_router_verdict: "REJECT",
    notes,
    authority:
      "recursive_twin_note_taker_twin_search_model_decision_compose_advisory",
  };
}

export function formatRecursiveTwinNoteTakerTwinSearchModelDecisionSummary(
  c: RecursiveTwinNoteTakerTwinSearchModelDecisionCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `twin_propose_ready=${c.twin.twin_propose_ready} · ` +
    `hits=${c.twin_search_pack.hit_count} · ` +
    `parent_aligned=${c.parent_aligned} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `twin_written=false · remote_index_queried=false · pdf_primary=false`
  );
}
