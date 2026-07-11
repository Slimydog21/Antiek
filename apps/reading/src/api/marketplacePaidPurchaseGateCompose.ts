/**
 * Marketplace paid purchase gate compose (pure).
 *
 * Operator vision: when no free PDF/HTML is available, allow buying a digital
 * book under an approved price ceiling, then seamless HTML port into account.
 * Free path is always preferred; purchase never executes in pure layer.
 *
 * purchase_executed always false.
 * hosted always false.
 * pdf_view_authorized always false.
 * charge_executed always false.
 */

import {
  composeMarketplaceFreeBeforeBuyHtmlPort,
  type MarketplaceFreeBeforeBuyHtmlPortCompose,
} from "./marketplaceFreeBeforeBuyHtmlPortCompose";

export interface MarketplacePaidPurchaseGateInput {
  title: string;
  account_id: string;
  /** Free online copy known available? null = unknown honesty. */
  free_copy_available: boolean | null;
  free_html_projection_sha?: string | null;
  purchase_html_projection_sha?: string | null;
  port_requested: boolean;
  /** Explicit operator ack to enter paid path when free unavailable. */
  purchase_ack: boolean;
  /**
   * List price of digital book (USD). Required for purchase_ready when
   * free is false. Null = unknown (never invent $0).
   */
  list_price_usd: number | null;
  /** Operator-approved max spend for this title. */
  approved_spend_usd: number | null;
  /** Remaining account/marketplace budget for purchases. null = unknown. */
  remaining_budget_usd: number | null;
  operator_ack: boolean;
}

export interface MarketplacePaidPurchaseGateCompose {
  free_port: MarketplaceFreeBeforeBuyHtmlPortCompose;
  list_price_usd: number | null;
  approved_spend_usd: number | null;
  remaining_budget_usd: number | null;
  /**
   * True when free is false, purchase_ack, prices known, approved >= list,
   * remaining covers list (when remaining known), and operator_ack.
   * Still never charges.
   */
  purchase_ready: boolean;
  /** null when list or remaining unknown — never invent false safety. */
  would_exceed_budget: boolean | null;
  /**
   * True when free path port_ready OR (purchase_ready and port_ready with sha).
   */
  gate_ready: boolean;
  purchase_executed: false;
  charge_executed: false;
  hosted: false;
  pdf_view_authorized: false;
  notes: string[];
  authority: "marketplace_paid_purchase_gate_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function finiteMoney(value: unknown, name: string): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${name} must be finite number or null`);
  }
  if (value < 0) {
    throw new Error(`${name} must be >= 0`);
  }
  return value;
}

/**
 * Compose paid purchase gate over free-before-buy HTML port.
 * Never purchases, charges, or hosts.
 */
export function composeMarketplacePaidPurchaseGate(
  input: MarketplacePaidPurchaseGateInput,
): MarketplacePaidPurchaseGateCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (typeof input.purchase_ack !== "boolean") {
    throw new Error("purchase_ack must be an explicit boolean");
  }
  if (typeof input.port_requested !== "boolean") {
    throw new Error("port_requested must be an explicit boolean");
  }

  const title = requireNonEmpty(input.title, "title");
  const account_id = requireNonEmpty(input.account_id, "account_id");
  const list_price_usd = finiteMoney(input.list_price_usd, "list_price_usd");
  const approved_spend_usd = finiteMoney(
    input.approved_spend_usd,
    "approved_spend_usd",
  );
  const remaining_budget_usd = finiteMoney(
    input.remaining_budget_usd,
    "remaining_budget_usd",
  );

  const notes: string[] = [
    "purchase_executed=false — paid gate never charges",
    "charge_executed=false — no payment processor call",
    "hosted=false — pure layer never hosts account assets",
    "pdf_view_authorized=false — HTML-native port only",
  ];

  const free_port = composeMarketplaceFreeBeforeBuyHtmlPort({
    title,
    account_id,
    free_copy_available: input.free_copy_available,
    free_html_projection_sha: input.free_html_projection_sha,
    purchase_ack: input.purchase_ack,
    port_requested: input.port_requested,
    purchase_html_projection_sha: input.purchase_html_projection_sha,
  });
  notes.push(...free_port.notes);

  let would_exceed_budget: boolean | null = null;
  if (list_price_usd === null || remaining_budget_usd === null) {
    would_exceed_budget = null;
    notes.push(
      "would_exceed_budget=null — list_price or remaining_budget unknown (no invent false)",
    );
  } else {
    would_exceed_budget = list_price_usd > remaining_budget_usd;
    notes.push(
      would_exceed_budget
        ? `would_exceed_budget=true (list=${list_price_usd} > remaining=${remaining_budget_usd})`
        : `would_exceed_budget=false (list=${list_price_usd} <= remaining=${remaining_budget_usd})`,
    );
  }

  let purchase_ready = false;
  if (input.free_copy_available === true) {
    notes.push(
      "purchase_ready=false — free copy available; free path preferred (no paid path)",
    );
  } else if (input.free_copy_available === null) {
    notes.push(
      "purchase_ready=false — free availability unknown; resolve free before buy",
    );
  } else if (!input.purchase_ack) {
    notes.push("purchase_ready=false — purchase_ack required when free unavailable");
  } else if (!input.operator_ack) {
    notes.push("purchase_ready=false — operator_ack required for paid gate");
  } else if (list_price_usd === null) {
    notes.push("purchase_ready=false — list_price_usd unknown (no invent $0)");
  } else if (approved_spend_usd === null) {
    notes.push(
      "purchase_ready=false — approved_spend_usd unknown (operator ceiling required)",
    );
  } else if (approved_spend_usd < list_price_usd) {
    notes.push(
      `purchase_ready=false — approved_spend ${approved_spend_usd} < list ${list_price_usd}`,
    );
  } else if (would_exceed_budget === true) {
    notes.push("purchase_ready=false — would exceed remaining budget");
  } else if (would_exceed_budget === null) {
    notes.push(
      "purchase_ready=false — remaining_budget_usd unknown (fail closed)",
    );
  } else {
    purchase_ready = true;
    notes.push(
      "purchase_ready=true — paid intent only; still purchase_executed=false · charge_executed=false",
    );
  }

  // gate_ready: free port ready OR paid path purchase_ready with port_ready sha
  let gate_ready = false;
  if (input.free_copy_available === true && free_port.port_ready) {
    gate_ready = true;
    notes.push("gate_ready=true via free HTML port path");
  } else if (
    purchase_ready &&
    free_port.port_ready &&
    free_port.html_projection_sha != null
  ) {
    gate_ready = true;
    notes.push(
      "gate_ready=true via paid port intent (sha present; still not charged/hosted)",
    );
  } else if (purchase_ready && !free_port.port_ready) {
    notes.push(
      "gate_ready=false — purchase_ready but port not ready (sha/port_requested)",
    );
  } else {
    notes.push("gate_ready=false");
  }

  if (
    free_port.purchase_executed !== false ||
    free_port.hosted !== false ||
    free_port.pdf_view_authorized !== false
  ) {
    throw new Error("invariant: free_port honesty flags must remain false");
  }

  notes.push("purchase_executed=false");
  notes.push("charge_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");

  return {
    free_port,
    list_price_usd,
    approved_spend_usd,
    remaining_budget_usd,
    purchase_ready,
    would_exceed_budget,
    gate_ready,
    purchase_executed: false,
    charge_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    notes,
    authority: "marketplace_paid_purchase_gate_compose_advisory",
  };
}

export function formatMarketplacePaidPurchaseGateSummary(
  c: MarketplacePaidPurchaseGateCompose,
): string {
  const w =
    c.would_exceed_budget === null
      ? "would_exceed_budget=null"
      : `would_exceed_budget=${c.would_exceed_budget}`;
  return (
    `gate_ready=${c.gate_ready} · purchase_ready=${c.purchase_ready} · ` +
    `path=${c.free_port.path} · ${w} · ` +
    `purchase_executed=false · charge_executed=false · hosted=false · pdf_view_authorized=false`
  );
}
