/**
 * Marketplace free-before-buy HTML port + source-attach record→prompt pack (pure).
 *
 * Operator vision: pure reading marketplace — free HTML first, purchase only
 * when free unavailable; seamless HTML host intent — stacked with arxiv/substack
 * attach and record→prompt research pack. Never purchases, hosts, or fetches.
 *
 * purchase_executed / hosted always false.
 * remote_fetched / prompts_injected always false.
 * pdf_view_authorized / pdf_primary always false.
 * production_router_verdict always REJECT; live_router_authorized always false.
 */

import {
  composeMarketplaceFreeBeforeBuyHtmlPort,
  type MarketplaceFreeBeforeBuyHtmlPortCompose,
  type MarketplaceFreeBeforeBuyHtmlPortInput,
} from "./marketplaceFreeBeforeBuyHtmlPortCompose";
import {
  composeSourceAttachRecordPromptHtmlNativeMo,
  type SourceAttachRecordPromptHtmlNativeMoCompose,
  type SourceAttachRecordPromptHtmlNativeMoInput,
} from "./sourceAttachRecordPromptHtmlNativeMoCompose";

export interface MarketplaceFreeSourceAttachRecordPromptInput {
  market: MarketplaceFreeBeforeBuyHtmlPortInput;
  research: Omit<SourceAttachRecordPromptHtmlNativeMoInput, "operator_ack">;
  operator_ack: boolean;
  require_both?: boolean;
}

export interface MarketplaceFreeSourceAttachRecordPromptCompose {
  session_id: string;
  parent_asset_id: string;
  week_id: string;
  account_id: string;
  market: MarketplaceFreeBeforeBuyHtmlPortCompose;
  research: SourceAttachRecordPromptHtmlNativeMoCompose;
  pack_ready: boolean;
  purchase_executed: false;
  hosted: false;
  remote_fetched: false;
  prompts_injected: false;
  pdf_view_authorized: false;
  pdf_primary: false;
  twin_written: false;
  charge_executed: false;
  live_execution_authorized: false;
  draft_written: false;
  analysis_written: false;
  merge_executed: false;
  record_persisted: false;
  live_dispatch_authorized: false;
  secrets_stored: false;
  inventory_mutated: false;
  live_dispatched: false;
  pack_dispatched: false;
  backlog_mutated: false;
  store_mutated: false;
  production_router_verdict: "REJECT";
  live_router_authorized: false;
  notes: string[];
  authority: "marketplace_free_source_attach_record_prompt_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Free-before-buy marketplace HTML port + source-attach research pack.
 * Never purchases, hosts, remote-fetches, or injects prompts.
 */
export function composeMarketplaceFreeSourceAttachRecordPrompt(
  input: MarketplaceFreeSourceAttachRecordPromptInput,
): MarketplaceFreeSourceAttachRecordPromptCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (!input.market || typeof input.market !== "object") {
    throw new Error("market must be an object");
  }
  if (!input.research || typeof input.research !== "object") {
    throw new Error("research must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "purchase_executed=false · hosted=false",
    "remote_fetched=false · prompts_injected=false",
    "pdf_view_authorized=false · pdf_primary=false",
    "production_router_verdict=REJECT · live_router_authorized=false",
  ];

  const market = composeMarketplaceFreeBeforeBuyHtmlPort(input.market);
  notes.push(...market.notes.map((n) => `[market] ${n}`));

  const research = composeSourceAttachRecordPromptHtmlNativeMo({
    ...input.research,
    operator_ack: input.operator_ack,
  });
  notes.push(...research.notes.map((n) => `[research] ${n}`));

  const session_id = requireNonEmpty(research.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    research.parent_asset_id,
    "parent_asset_id",
  );
  const week_id = requireNonEmpty(research.week_id, "week_id");
  const account_id = requireNonEmpty(market.account_id, "account_id");

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      market.port_ready === true &&
      research.pack_ready === true &&
      research.production_router_verdict === "REJECT" &&
      market.purchase_executed === false &&
      market.hosted === false &&
      research.remote_fetched === false &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      research.production_router_verdict === "REJECT" &&
      market.purchase_executed === false &&
      (market.port_ready === true || research.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — free-before-buy HTML port + source-attach research ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — market, research, or operator_ack gate open",
    );
  }

  if (
    market.purchase_executed !== false ||
    market.hosted !== false ||
    market.pdf_view_authorized !== false ||
    research.remote_fetched !== false ||
    research.prompts_injected !== false ||
    research.pdf_primary !== false ||
    research.production_router_verdict !== "REJECT" ||
    research.live_router_authorized !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("remote_fetched=false");
  notes.push("prompts_injected=false");
  notes.push("pdf_view_authorized=false");
  notes.push("pdf_primary=false");
  notes.push("twin_written=false");
  notes.push("charge_executed=false");
  notes.push("live_execution_authorized=false");
  notes.push("draft_written=false");
  notes.push("analysis_written=false");
  notes.push("merge_executed=false");
  notes.push("record_persisted=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("secrets_stored=false");
  notes.push("inventory_mutated=false");
  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");
  notes.push("production_router_verdict=REJECT");
  notes.push("live_router_authorized=false");

  return {
    session_id,
    parent_asset_id,
    week_id,
    account_id,
    market,
    research,
    pack_ready,
    purchase_executed: false,
    hosted: false,
    remote_fetched: false,
    prompts_injected: false,
    pdf_view_authorized: false,
    pdf_primary: false,
    twin_written: false,
    charge_executed: false,
    live_execution_authorized: false,
    draft_written: false,
    analysis_written: false,
    merge_executed: false,
    record_persisted: false,
    live_dispatch_authorized: false,
    secrets_stored: false,
    inventory_mutated: false,
    live_dispatched: false,
    pack_dispatched: false,
    backlog_mutated: false,
    store_mutated: false,
    production_router_verdict: "REJECT",
    live_router_authorized: false,
    notes,
    authority: "marketplace_free_source_attach_record_prompt_compose_advisory",
  };
}

export function formatMarketplaceFreeSourceAttachRecordPromptSummary(
  c: MarketplaceFreeSourceAttachRecordPromptCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `market_path=${c.market.path} · ` +
    `port_ready=${c.market.port_ready} · ` +
    `research_ready=${c.research.pack_ready} · ` +
    `verdict=${c.production_router_verdict} · ` +
    `purchase_executed=false · hosted=false · remote_fetched=false`
  );
}
