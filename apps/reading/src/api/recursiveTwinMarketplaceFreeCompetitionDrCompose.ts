/**
 * Recursive twin note-taker over marketplace free + competition DR pack (pure).
 *
 * Operator vision: every information asset has a twin document of insights and
 * questions (LLM as perfect note-taker). Propose that twin substrate over the
 * free-first marketplace HTML port + competition DR quality + settings BYOK +
 * Antiek-bench + source-attach + Midnight Oil pack — without writing twins,
 * purchasing, hosting, or live-dispatching.
 *
 * twin_written / prompts_injected / live_dispatch_authorized always false.
 * purchase_executed / hosted always false.
 * secrets_stored / inventory_mutated / live_router_authorized always false.
 * production_router_verdict always REJECT.
 */

import {
  composeRecursiveTwinNoteTaker,
  type RecursiveTwinNoteTakerCompose,
  type RecursiveTwinNoteTakerInput,
} from "./recursiveTwinNoteTakerCompose";
import {
  composeMarketplaceFreeCompetitionDrSettingsBenchMo,
  type MarketplaceFreeCompetitionDrSettingsBenchMoCompose,
  type MarketplaceFreeCompetitionDrSettingsBenchMoInput,
} from "./marketplaceFreeCompetitionDrSettingsBenchMoCompose";

export interface RecursiveTwinMarketplaceFreeCompetitionDrInput {
  twin: Omit<RecursiveTwinNoteTakerInput, "operator_ack">;
  market_pack: Omit<
    MarketplaceFreeCompetitionDrSettingsBenchMoInput,
    "operator_ack"
  >;
  operator_ack: boolean;
  /**
   * When true (default), require twin.twin_propose_ready AND
   * market_pack.pack_ready, and parent_asset_id alignment.
   */
  require_both?: boolean;
}

export interface RecursiveTwinMarketplaceFreeCompetitionDrCompose {
  session_id: string;
  parent_asset_id: string;
  title: string;
  account_id: string;
  week_id: string;
  focus_task: string;
  asset_id: string;
  twin: RecursiveTwinNoteTakerCompose;
  market_pack: MarketplaceFreeCompetitionDrSettingsBenchMoCompose;
  /** Soft: twin.parent_asset_id matches market_pack.parent_asset_id. */
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
  authority: "recursive_twin_marketplace_free_competition_dr_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Recursive twin note-taker stacked on marketplace free competition DR pack.
 * Never writes twins; never purchases/hosts; never live-dispatches.
 */
export function composeRecursiveTwinMarketplaceFreeCompetitionDr(
  input: RecursiveTwinMarketplaceFreeCompetitionDrInput,
): RecursiveTwinMarketplaceFreeCompetitionDrCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.twin || typeof input.twin !== "object") {
    throw new Error("twin must be an object");
  }
  if (!input.market_pack || typeof input.market_pack !== "object") {
    throw new Error("market_pack must be an object");
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
    "purchase_executed=false · hosted=false",
    "production_router_verdict=REJECT",
  ];

  const twin = composeRecursiveTwinNoteTaker({
    ...input.twin,
    operator_ack: input.operator_ack,
  });
  notes.push(...twin.notes.map((n) => `[twin] ${n}`));

  const market_pack = composeMarketplaceFreeCompetitionDrSettingsBenchMo({
    ...input.market_pack,
    operator_ack: input.operator_ack,
  });
  notes.push(...market_pack.notes.map((n) => `[market_pack] ${n}`));

  const parent_asset_id = requireNonEmpty(
    twin.parent_asset_id,
    "parent_asset_id",
  );
  const session_id = requireNonEmpty(market_pack.session_id, "session_id");
  const title = requireNonEmpty(market_pack.title, "title");
  const account_id = requireNonEmpty(market_pack.account_id, "account_id");
  const week_id = requireNonEmpty(market_pack.week_id, "week_id");
  const focus_task = requireNonEmpty(market_pack.focus_task, "focus_task");
  const asset_id = requireNonEmpty(market_pack.asset_id, "asset_id");

  const market_parent = requireNonEmpty(
    market_pack.parent_asset_id,
    "market_pack.parent_asset_id",
  );
  const parent_aligned = parent_asset_id === market_parent;
  if (!parent_aligned) {
    notes.push(
      `parent_aligned=false — twin.parent=${parent_asset_id} market_pack.parent=${market_parent}`,
    );
  } else {
    notes.push("parent_aligned=true");
  }

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      twin.twin_propose_ready === true &&
      market_pack.pack_ready === true &&
      parent_aligned === true &&
      twin.twin_written === false &&
      twin.prompts_injected === false &&
      twin.live_dispatch_authorized === false &&
      market_pack.purchase_executed === false &&
      market_pack.hosted === false &&
      market_pack.pdf_view_authorized === false &&
      market_pack.live_dispatch_authorized === false &&
      market_pack.remote_fetched === false &&
      market_pack.backlog_mutated === false &&
      market_pack.inventory_mutated === false &&
      market_pack.secrets_stored === false &&
      market_pack.live_router_authorized === false &&
      market_pack.suite_rewritten === false &&
      market_pack.live_execution_authorized === false &&
      market_pack.production_router_verdict === "REJECT" &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      twin.twin_written === false &&
      twin.prompts_injected === false &&
      twin.live_dispatch_authorized === false &&
      market_pack.purchase_executed === false &&
      market_pack.hosted === false &&
      market_pack.production_router_verdict === "REJECT" &&
      (twin.twin_propose_ready === true || market_pack.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — recursive twin + marketplace free competition DR ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — twin, market_pack, parent align, or operator_ack gate open",
    );
  }

  if (
    twin.twin_written !== false ||
    twin.prompts_injected !== false ||
    twin.live_dispatch_authorized !== false ||
    market_pack.purchase_executed !== false ||
    market_pack.hosted !== false ||
    market_pack.pdf_view_authorized !== false ||
    market_pack.live_dispatch_authorized !== false ||
    market_pack.remote_fetched !== false ||
    market_pack.backlog_mutated !== false ||
    market_pack.inventory_mutated !== false ||
    market_pack.secrets_stored !== false ||
    market_pack.live_router_authorized !== false ||
    market_pack.suite_rewritten !== false ||
    market_pack.live_execution_authorized !== false ||
    market_pack.production_router_verdict !== "REJECT"
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
    focus_task,
    asset_id,
    twin,
    market_pack,
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
      "recursive_twin_marketplace_free_competition_dr_compose_advisory",
  };
}

export function formatRecursiveTwinMarketplaceFreeCompetitionDrSummary(
  c: RecursiveTwinMarketplaceFreeCompetitionDrCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `twin_propose=${c.twin.twin_propose_ready} · ` +
    `market_ready=${c.market_pack.pack_ready} · ` +
    `parent_aligned=${c.parent_aligned} · ` +
    `week=${c.week_id} · task=${c.focus_task} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `twin_written=false · purchase_executed=false · hosted=false · live_dispatch_authorized=false`
  );
}
