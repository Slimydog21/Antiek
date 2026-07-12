/**
 * Marketplace HTML book session → highlight float → recursive twin MO (pure).
 *
 * Operator vision: free-first or paid digital book hosted as HTML in account,
 * then engage as research workstation — highlight float deep research, model
 * decision, competition quality, midnight oil, recursive twin note-taker —
 * without purchase charge, PDF primary, or live workers.
 *
 * purchase_executed / charge_executed / hosted / pdf_view_authorized always false.
 * live_dispatched / twin_written / live_execution_authorized always false.
 */

import {
  composeMarketplaceHtmlViewTwinSession,
  type MarketplaceHtmlViewTwinSessionCompose,
  type MarketplaceHtmlViewTwinSessionInput,
} from "./marketplaceHtmlViewTwinSessionCompose";
import {
  composeHighlightFloatRecursiveTwinMoCompetition,
  type HighlightFloatRecursiveTwinMoCompetitionCompose,
  type HighlightFloatRecursiveTwinMoCompetitionInput,
} from "./highlightFloatRecursiveTwinMoCompetitionCompose";
import type { ReadingHighlightFloatTwinFeedInput } from "./readingHighlightFloatTwinFeedCompose";

export interface MarketplaceHighlightFloatRecursiveTwinMoInput {
  market: MarketplaceHtmlViewTwinSessionInput;
  /**
   * Research pack inputs. highlight_surface.session_id/parent_asset_id may
   * omit and default from marketplace session/asset.
   */
  research: {
    highlight_surface: Omit<
      ReadingHighlightFloatTwinFeedInput,
      "session_id" | "parent_asset_id" | "operator_ack" | "highlight"
    > & {
      session_id?: string;
      parent_asset_id?: string;
      /** When omitted and seed_highlight_from_title, uses book title. */
      highlight?: string;
    };
    mo_competition: HighlightFloatRecursiveTwinMoCompetitionInput["mo_competition"];
    seed_excerpt_from_highlight?: boolean;
    require_both?: boolean;
  };
  operator_ack: boolean;
  /**
   * When true (default), seed highlight from market title when highlight omitted.
   */
  seed_highlight_from_title?: boolean;
  require_both?: boolean;
}

export interface MarketplaceHighlightFloatRecursiveTwinMoCompose {
  session_id: string;
  asset_id: string;
  market: MarketplaceHtmlViewTwinSessionCompose;
  research: HighlightFloatRecursiveTwinMoCompetitionCompose;
  pack_ready: boolean;
  purchase_executed: false;
  charge_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  live_dispatched: false;
  merge_executed: false;
  pack_dispatched: false;
  twin_written: false;
  record_persisted: false;
  live_execution_authorized: false;
  prompts_injected: false;
  live_router_authorized: false;
  store_mutated: false;
  notes: string[];
  authority: "marketplace_highlight_float_recursive_twin_mo_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose marketplace HTML/twin session with highlight float → twin MO pack.
 * Never purchases, hosts, PDF-views, or launches live workers.
 */
export function composeMarketplaceHighlightFloatRecursiveTwinMo(
  input: MarketplaceHighlightFloatRecursiveTwinMoInput,
): MarketplaceHighlightFloatRecursiveTwinMoCompose {
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
  if (
    !input.research.highlight_surface ||
    typeof input.research.highlight_surface !== "object"
  ) {
    throw new Error("research.highlight_surface must be an object");
  }

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }
  const seed_title =
    input.seed_highlight_from_title === undefined
      ? true
      : input.seed_highlight_from_title;
  if (typeof seed_title !== "boolean") {
    throw new Error("seed_highlight_from_title must be boolean when set");
  }

  const notes: string[] = [
    "purchase_executed=false · charge_executed=false · hosted=false",
    "pdf_view_authorized=false — HTML-native marketplace + reading",
    "live_dispatched=false · twin_written=false · live_execution_authorized=false",
    "prompts_injected=false · live_router_authorized=false · store_mutated=false",
  ];

  const market = composeMarketplaceHtmlViewTwinSession({
    ...input.market,
    operator_ack: input.operator_ack,
  });
  notes.push(...market.notes.map((n) => `[market] ${n}`));

  const session_id = requireNonEmpty(market.session_id, "session_id");
  const asset_id = requireNonEmpty(market.asset_id, "asset_id");

  const hs = input.research.highlight_surface;
  let highlight: string;
  if (hs.highlight != null && String(hs.highlight).trim()) {
    highlight = String(hs.highlight).trim();
  } else if (seed_title) {
    highlight = `from book: ${requireNonEmpty(input.market.title, "market.title")}`;
    notes.push("highlight seeded from marketplace book title");
  } else {
    throw new Error(
      "research.highlight_surface.highlight must be non-empty when seed_highlight_from_title=false",
    );
  }

  const highlight_surface: ReadingHighlightFloatTwinFeedInput = {
    ...hs,
    session_id: hs.session_id?.trim() || session_id,
    parent_asset_id: hs.parent_asset_id?.trim() || asset_id,
    highlight,
    operator_ack: input.operator_ack,
  };

  const mo_competition = {
    ...input.research.mo_competition,
    parent_asset_id:
      input.research.mo_competition.parent_asset_id?.trim() || asset_id,
  };

  const research = composeHighlightFloatRecursiveTwinMoCompetition({
    highlight_surface,
    mo_competition,
    operator_ack: input.operator_ack,
    seed_excerpt_from_highlight: input.research.seed_excerpt_from_highlight,
    require_both: input.research.require_both,
  });
  notes.push(...research.notes.map((n) => `[research] ${n}`));

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      market.session_ready === true &&
      research.pack_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (market.session_ready === true || research.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — marketplace HTML book + highlight float twin MO ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — market, research, or operator_ack gate open",
    );
  }

  if (
    market.purchase_executed !== false ||
    market.charge_executed !== false ||
    market.hosted !== false ||
    market.pdf_view_authorized !== false ||
    market.twin_written !== false ||
    research.live_dispatched !== false ||
    research.twin_written !== false ||
    research.live_execution_authorized !== false ||
    research.prompts_injected !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("purchase_executed=false");
  notes.push("charge_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("pack_dispatched=false");
  notes.push("twin_written=false");
  notes.push("record_persisted=false");
  notes.push("live_execution_authorized=false");
  notes.push("prompts_injected=false");
  notes.push("live_router_authorized=false");
  notes.push("store_mutated=false");

  return {
    session_id,
    asset_id,
    market,
    research,
    pack_ready,
    purchase_executed: false,
    charge_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    live_dispatched: false,
    merge_executed: false,
    pack_dispatched: false,
    twin_written: false,
    record_persisted: false,
    live_execution_authorized: false,
    prompts_injected: false,
    live_router_authorized: false,
    store_mutated: false,
    notes,
    authority: "marketplace_highlight_float_recursive_twin_mo_compose_advisory",
  };
}

export function formatMarketplaceHighlightFloatRecursiveTwinMoSummary(
  c: MarketplaceHighlightFloatRecursiveTwinMoCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `market_ready=${c.market.session_ready} · ` +
    `research_ready=${c.research.pack_ready} · ` +
    `purchase_executed=false · hosted=false · pdf_view_authorized=false · ` +
    `live_dispatched=false · twin_written=false · live_execution_authorized=false`
  );
}
