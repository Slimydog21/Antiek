/**
 * Paid purchase → HTML view session compose (pure).
 *
 * Operator vision: after marketplace paid (or free) gate is ready, open an
 * HTML-native reading session for the book in-account — never PDF primary.
 *
 * purchase_executed / charge_executed / hosted always false.
 * pdf_view_authorized always false.
 * store_mutated always false.
 */

import {
  composeMarketplacePaidPurchaseGate,
  type MarketplacePaidPurchaseGateCompose,
} from "./marketplacePaidPurchaseGateCompose";
import {
  composeHtmlAssetViewSession,
  type HtmlAssetViewSessionCompose,
} from "./htmlAssetViewSessionCompose";

export interface PaidPurchaseHtmlViewSessionInput {
  session_id: string;
  /** Asset id for the HTML view session (account-hosted book id). */
  asset_id: string;
  title: string;
  account_id: string;
  free_copy_available: boolean | null;
  free_html_projection_sha?: string | null;
  purchase_html_projection_sha?: string | null;
  port_requested: boolean;
  purchase_ack: boolean;
  list_price_usd: number | null;
  approved_spend_usd: number | null;
  remaining_budget_usd: number | null;
  operator_ack: boolean;
  view_requested: boolean;
  twin_bound?: boolean;
  twin_substrate_ready?: boolean;
  claimed_format?: string | null;
}

export interface PaidPurchaseHtmlViewSessionCompose {
  purchase_gate: MarketplacePaidPurchaseGateCompose;
  view: HtmlAssetViewSessionCompose | null;
  /**
   * True when purchase/free gate_ready and html_view session_ready.
   */
  session_package_ready: boolean;
  purchase_executed: false;
  charge_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  store_mutated: false;
  notes: string[];
  authority: "paid_purchase_html_view_session_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose marketplace gate + HTML view session for seamless book open.
 * Never purchases, hosts, or authorizes PDF.
 */
export function composePaidPurchaseHtmlViewSession(
  input: PaidPurchaseHtmlViewSessionInput,
): PaidPurchaseHtmlViewSessionCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (typeof input.view_requested !== "boolean") {
    throw new Error("view_requested must be an explicit boolean");
  }

  const session_id = requireNonEmpty(input.session_id, "session_id");
  const asset_id = requireNonEmpty(input.asset_id, "asset_id");

  const notes: string[] = [
    "purchase_executed=false · charge_executed=false · hosted=false",
    "pdf_view_authorized=false — HTML-native only",
    "store_mutated=false — pure session pack",
  ];

  const purchase_gate = composeMarketplacePaidPurchaseGate({
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
  });
  notes.push(...purchase_gate.notes);

  // Prefer sha from free_port when gate ready
  const sha =
    purchase_gate.free_port.html_projection_sha ??
    input.purchase_html_projection_sha ??
    input.free_html_projection_sha ??
    null;

  let view: HtmlAssetViewSessionCompose | null = null;
  if (purchase_gate.gate_ready || input.view_requested) {
    view = composeHtmlAssetViewSession({
      session_id,
      asset_id,
      html_projection_sha: sha,
      view_requested: input.view_requested,
      twin_bound: input.twin_bound === true,
      twin_substrate_ready: input.twin_substrate_ready,
      claimed_format: input.claimed_format,
    });
    notes.push(...view.notes);
  } else {
    notes.push("view session not composed — gate not ready and view not requested");
  }

  const session_package_ready =
    purchase_gate.gate_ready &&
    view != null &&
    view.session_ready === true &&
    view.pdf_view_authorized === false;

  if (!purchase_gate.gate_ready) {
    notes.push("session_package_ready=false — marketplace gate not ready");
  } else if (view == null || !view.session_ready) {
    notes.push("session_package_ready=false — HTML view session not ready");
  } else {
    notes.push(
      "session_package_ready=true — HTML open intent; still not purchased/hosted",
    );
  }

  if (
    purchase_gate.purchase_executed !== false ||
    purchase_gate.charge_executed !== false ||
    purchase_gate.hosted !== false ||
    purchase_gate.pdf_view_authorized !== false
  ) {
    throw new Error("invariant: purchase gate honesty flags must remain false");
  }
  if (
    view != null &&
    (view.pdf_view_authorized !== false || view.store_mutated !== false)
  ) {
    throw new Error("invariant: view honesty flags must remain false");
  }

  notes.push("purchase_executed=false");
  notes.push("charge_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");
  notes.push("store_mutated=false");

  return {
    purchase_gate,
    view,
    session_package_ready,
    purchase_executed: false,
    charge_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    store_mutated: false,
    notes,
    authority: "paid_purchase_html_view_session_compose_advisory",
  };
}

export function formatPaidPurchaseHtmlViewSessionSummary(
  c: PaidPurchaseHtmlViewSessionCompose,
): string {
  return (
    `session_package_ready=${c.session_package_ready} · ` +
    `gate_ready=${c.purchase_gate.gate_ready} · ` +
    `html_view_ready=${c.view ? c.view.html_view_ready : "n/a"} · ` +
    `purchase_executed=false · charge_executed=false · hosted=false · ` +
    `pdf_view_authorized=false · store_mutated=false`
  );
}
