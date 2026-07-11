/**
 * Marketplace HTML view + twin session compose (pure).
 *
 * Operator vision: free-first or paid digital book → HTML host path → open
 * HTML-native reading session with twin note-taker substrate ready for
 * recursive insights/questions. Never PDF primary; never charges/hosts live.
 *
 * purchase_executed / charge_executed / hosted always false.
 * pdf_view_authorized always false.
 * twin_written / record_persisted always false.
 * store_mutated always false.
 */

import {
  composePaidPurchaseHtmlViewSession,
  type PaidPurchaseHtmlViewSessionCompose,
  type PaidPurchaseHtmlViewSessionInput,
} from "./paidPurchaseHtmlViewSessionCompose";
import {
  composeTwinChaseAnalysisFeed,
  type ChaseFeedFinding,
  type TwinChaseAnalysisFeedCompose,
} from "./twinChaseAnalysisFeedCompose";

export interface MarketplaceHtmlViewTwinSessionInput
  extends PaidPurchaseHtmlViewSessionInput {
  /**
   * Optional twin findings beyond title seed (caller-supplied).
   * Title is always seeded as a data finding when twin feed is included.
   */
  twin_findings?: ChaseFeedFinding[] | null;
  existing_twin_asset_id?: string | null;
  mark_for_prompt_context?: boolean;
  /** Default true — twin feed for book reading engagement. */
  include_twin_feed?: boolean;
}

export interface MarketplaceHtmlViewTwinSessionCompose {
  session_id: string;
  asset_id: string;
  market_view: PaidPurchaseHtmlViewSessionCompose;
  twin_feed: TwinChaseAnalysisFeedCompose | null;
  /**
   * True when market_view.session_package_ready and
   * (twin skipped or twin feed_ready).
   */
  session_ready: boolean;
  purchase_executed: false;
  charge_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  twin_written: false;
  record_persisted: false;
  store_mutated: false;
  notes: string[];
  authority: "marketplace_html_view_twin_session_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose marketplace free/paid gate → HTML view session → twin feed.
 * Never purchases, hosts, PDF-views, or writes twins.
 */
export function composeMarketplaceHtmlViewTwinSession(
  input: MarketplaceHtmlViewTwinSessionInput,
): MarketplaceHtmlViewTwinSessionCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const asset_id = requireNonEmpty(input.asset_id, "asset_id");
  const include_twin =
    input.include_twin_feed === undefined ? true : input.include_twin_feed;
  if (typeof include_twin !== "boolean") {
    throw new Error("include_twin_feed must be boolean when set");
  }

  const notes: string[] = [
    "purchase_executed=false · charge_executed=false · hosted=false",
    "pdf_view_authorized=false — HTML-native only",
    "twin_written=false · record_persisted=false · store_mutated=false",
  ];

  // Prefer twin_bound when twin feed included
  const marketInput: PaidPurchaseHtmlViewSessionInput = {
    session_id: input.session_id,
    asset_id: input.asset_id,
    title: input.title,
    account_id: input.account_id,
    free_copy_available: input.free_copy_available,
    free_html_projection_sha: input.free_html_projection_sha,
    purchase_html_projection_sha: input.purchase_html_projection_sha,
    port_requested: input.port_requested,
    purchase_ack: input.purchase_ack,
    list_price_usd: input.list_price_usd,
    approved_spend_usd: input.approved_spend_usd,
    remaining_budget_usd: input.remaining_budget_usd,
    operator_ack: input.operator_ack,
    view_requested: input.view_requested,
    twin_bound:
      input.twin_bound === undefined ? include_twin : input.twin_bound,
    twin_substrate_ready: input.twin_substrate_ready,
    claimed_format: input.claimed_format,
  };
  const market_view = composePaidPurchaseHtmlViewSession(marketInput);
  notes.push(...market_view.notes);

  let twin_feed: TwinChaseAnalysisFeedCompose | null = null;
  if (include_twin) {
    const title = requireNonEmpty(input.title, "title");
    const findings: ChaseFeedFinding[] = [
      {
        source_id: `book_title_${asset_id}`,
        body: title,
        kind: "data",
      },
    ];
    if (input.twin_findings != null) {
      if (!Array.isArray(input.twin_findings)) {
        throw new Error("twin_findings must be an array when set");
      }
      for (const f of input.twin_findings) {
        findings.push(f);
      }
    }
    twin_feed = composeTwinChaseAnalysisFeed({
      session_id,
      parent_asset_id: asset_id,
      findings,
      analysis_excerpt: `HTML reading session for: ${title}`,
      existing_twin_asset_id: input.existing_twin_asset_id,
      operator_ack: input.operator_ack,
      mark_for_prompt_context: input.mark_for_prompt_context,
    });
    notes.push(...twin_feed.notes);
  } else {
    notes.push("twin_feed skipped — include_twin_feed=false");
  }

  const twin_ok = !include_twin || (twin_feed != null && twin_feed.feed_ready);
  const session_ready = market_view.session_package_ready && twin_ok;

  if (!market_view.session_package_ready) {
    notes.push(
      "session_ready=false — marketplace/HTML view package not ready",
    );
  } else if (!twin_ok) {
    notes.push("session_ready=false — twin feed not ready");
  } else {
    notes.push(
      "session_ready=true — marketplace HTML+twin intent only; still pure",
    );
  }

  if (
    market_view.purchase_executed !== false ||
    market_view.charge_executed !== false ||
    market_view.hosted !== false ||
    market_view.pdf_view_authorized !== false ||
    market_view.store_mutated !== false ||
    (twin_feed != null &&
      (twin_feed.twin_written !== false ||
        twin_feed.record_persisted !== false ||
        twin_feed.live_dispatch_authorized !== false))
  ) {
    throw new Error("invariant: nested honesty flags must remain false");
  }

  notes.push("purchase_executed=false");
  notes.push("charge_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("twin_written=false");
  notes.push("record_persisted=false");
  notes.push("store_mutated=false");

  return {
    session_id,
    asset_id,
    market_view,
    twin_feed,
    session_ready,
    purchase_executed: false,
    charge_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    twin_written: false,
    record_persisted: false,
    store_mutated: false,
    notes,
    authority: "marketplace_html_view_twin_session_compose_advisory",
  };
}

export function formatMarketplaceHtmlViewTwinSessionSummary(
  c: MarketplaceHtmlViewTwinSessionCompose,
): string {
  return (
    `session_ready=${c.session_ready} · ` +
    `market_package_ready=${c.market_view.session_package_ready} · ` +
    `feed_ready=${c.twin_feed ? c.twin_feed.feed_ready : "n/a"} · ` +
    `purchase_executed=false · charge_executed=false · hosted=false · ` +
    `pdf_view_authorized=false · twin_written=false · record_persisted=false`
  );
}
