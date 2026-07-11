/**
 * Marketplace free-before-buy → HTML port compose (pure).
 *
 * Operator vision: pure reading mode — buy digital book only if no free PDF/
 * HTML online; then seamless port so the book is hosted as HTML in account.
 *
 * Builds on free-first doctrine. Never invents free hits or purchase.
 * purchase_executed always false.
 * hosted always false.
 * pdf_view_authorized always false (HTML-native port).
 */

export type FreeBeforeBuyPortPath =
  | "prefer_free_html"
  | "prefer_free_then_port"
  | "purchase_then_port"
  | "blocked_unknown_free"
  | "incomplete";

export interface MarketplaceFreeBeforeBuyHtmlPortInput {
  title: string;
  account_id: string;
  /** Free online copy known available? null = unknown honesty. */
  free_copy_available: boolean | null;
  /** Free copy already projected as HTML (caller-supplied sha). */
  free_html_projection_sha?: string | null;
  /** Operator explicitly opts into purchase path when free unavailable. */
  purchase_ack: boolean;
  /** Operator wants port into account after free or purchase readiness. */
  port_requested: boolean;
  /** Optional purchase-side ready HTML sha (still not hosted here). */
  purchase_html_projection_sha?: string | null;
}

export interface MarketplaceFreeBeforeBuyHtmlPortCompose {
  title: string;
  account_id: string;
  path: FreeBeforeBuyPortPath;
  /** True when a port intent is valid (sha present + port_requested). */
  port_ready: boolean;
  html_projection_sha: string | null;
  /** Always false — pure layer never executes purchase. */
  purchase_executed: false;
  /** Always false — pure layer never hosts account bytes. */
  hosted: false;
  /** Always false — HTML-native doctrine. */
  pdf_view_authorized: false;
  notes: string[];
  authority: "marketplace_free_before_buy_html_port_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose free-before-buy HTML port intent for a book title into an account.
 * Never purchases; never hosts; never authorizes PDF view.
 */
export function composeMarketplaceFreeBeforeBuyHtmlPort(
  input: MarketplaceFreeBeforeBuyHtmlPortInput,
): MarketplaceFreeBeforeBuyHtmlPortCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.purchase_ack !== "boolean") {
    throw new Error("purchase_ack must be an explicit boolean");
  }
  if (typeof input.port_requested !== "boolean") {
    throw new Error("port_requested must be an explicit boolean");
  }
  const title = requireNonEmpty(input.title, "title");
  const account_id = requireNonEmpty(input.account_id, "account_id");

  if (
    input.free_copy_available !== null &&
    input.free_copy_available !== undefined &&
    typeof input.free_copy_available !== "boolean"
  ) {
    throw new Error("free_copy_available must be boolean or null");
  }
  const free_copy_available =
    input.free_copy_available === undefined ? null : input.free_copy_available;

  let free_sha: string | null = null;
  if (
    input.free_html_projection_sha != null &&
    input.free_html_projection_sha !== undefined
  ) {
    free_sha = requireNonEmpty(
      input.free_html_projection_sha,
      "free_html_projection_sha",
    );
  }
  let purchase_sha: string | null = null;
  if (
    input.purchase_html_projection_sha != null &&
    input.purchase_html_projection_sha !== undefined
  ) {
    purchase_sha = requireNonEmpty(
      input.purchase_html_projection_sha,
      "purchase_html_projection_sha",
    );
  }

  const notes: string[] = [
    "purchase_executed=false — free-before-buy never auto-purchases",
    "hosted=false — pure layer never hosts account assets",
    "pdf_view_authorized=false — HTML-native port only",
  ];

  let path: FreeBeforeBuyPortPath = "incomplete";
  let html_projection_sha: string | null = null;
  let port_ready = false;

  if (free_copy_available === null) {
    path = "blocked_unknown_free";
    notes.push(
      "free_copy_available=null — fail closed; resolve free availability before buy/port",
    );
  } else if (free_copy_available === true) {
    if (free_sha) {
      path = "prefer_free_html";
      html_projection_sha = free_sha;
      port_ready = input.port_requested;
      notes.push(
        port_ready
          ? "path=prefer_free_html · port_ready=true (free HTML sha present)"
          : "path=prefer_free_html · port_ready=false (port_requested=false)",
      );
    } else {
      path = "prefer_free_then_port";
      port_ready = false;
      notes.push(
        "path=prefer_free_then_port · free available but free_html_projection_sha absent (no invent)",
      );
    }
  } else {
    // free not available
    if (!input.purchase_ack) {
      path = "incomplete";
      notes.push(
        "free unavailable · purchase_ack=false — operator must ack purchase path",
      );
    } else if (purchase_sha) {
      path = "purchase_then_port";
      html_projection_sha = purchase_sha;
      port_ready = input.port_requested;
      notes.push(
        port_ready
          ? "path=purchase_then_port · port_ready=true (purchase HTML sha; still purchase_executed=false)"
          : "path=purchase_then_port · port_ready=false (port_requested=false)",
      );
    } else {
      path = "purchase_then_port";
      port_ready = false;
      notes.push(
        "path=purchase_then_port · purchase_ack=true but purchase_html_projection_sha absent (no invent)",
      );
    }
  }

  notes.push("purchase_executed=false");
  notes.push("hosted=false");
  notes.push("pdf_view_authorized=false");

  return {
    title,
    account_id,
    path,
    port_ready,
    html_projection_sha,
    purchase_executed: false,
    hosted: false,
    pdf_view_authorized: false,
    notes,
    authority: "marketplace_free_before_buy_html_port_compose_advisory",
  };
}

export function formatMarketplaceFreeBeforeBuyHtmlPortSummary(
  c: MarketplaceFreeBeforeBuyHtmlPortCompose,
): string {
  return (
    `path=${c.path} · port_ready=${c.port_ready} · ` +
    `purchase_executed=false · hosted=false · pdf_view_authorized=false`
  );
}
