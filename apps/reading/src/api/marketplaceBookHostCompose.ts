/**
 * Marketplace free-copy → purchase → HTML host compose (pure).
 *
 * Operator vision: free-before-buy, then seamless HTML host in account.
 * This pure layer composes gate outcomes into a single decision.
 * Never invents free hit, purchase_executed, or hosted=true.
 */

export type MarketplacePath =
  | "free_copy"
  | "purchase_intent"
  | "html_host"
  | "blocked"
  | "incomplete";

export interface MarketplaceBookHostComposeInput {
  title: string;
  /** From free-copy preflight: freely available online? */
  free_copy_available: boolean | null;
  /** Operator skip free-copy with explicit ack. */
  skip_free_copy?: boolean;
  operator_skip_acknowledged?: boolean;
  /** Purchase intent allowed from purchase gate (not executed). */
  purchase_intent_allowed?: boolean | null;
  /** Ready HTML projection sha after free/purchase path. */
  html_projection_sha?: string | null;
  /** Operator wants HTML host after ready projection. */
  host_requested?: boolean;
}

export interface MarketplaceBookHostComposeDecision {
  title: string;
  path: MarketplacePath;
  free_copy_available: boolean | null;
  purchase_intent_allowed: boolean;
  /** Always false — pure compose never executes purchase. */
  purchase_executed: false;
  /** True only when path is html_host and sha present. */
  hostable: boolean;
  /** Always false — pure compose never hosts bytes. */
  hosted: false;
  html_projection_sha: string | null;
  notes: string[];
  authority: "marketplace_book_host_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose free-copy → purchase → HTML host decision for a book title.
 * Fail closed; never invents purchase_executed or hosted.
 */
export function composeMarketplaceBookHost(
  input: MarketplaceBookHostComposeInput,
): MarketplaceBookHostComposeDecision {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  const title = requireNonEmpty(input.title, "title");

  if (
    input.free_copy_available !== null &&
    input.free_copy_available !== undefined &&
    typeof input.free_copy_available !== "boolean"
  ) {
    throw new Error("free_copy_available must be boolean or null");
  }
  const free_copy_available =
    input.free_copy_available === undefined ? null : input.free_copy_available;

  const skip_free_copy =
    input.skip_free_copy === undefined ? false : input.skip_free_copy;
  if (typeof skip_free_copy !== "boolean") {
    throw new Error("skip_free_copy must be an explicit boolean when set");
  }
  const operator_skip_acknowledged =
    input.operator_skip_acknowledged === undefined
      ? false
      : input.operator_skip_acknowledged;
  if (typeof operator_skip_acknowledged !== "boolean") {
    throw new Error(
      "operator_skip_acknowledged must be an explicit boolean when set",
    );
  }

  const host_requested =
    input.host_requested === undefined ? true : input.host_requested;
  if (typeof host_requested !== "boolean") {
    throw new Error("host_requested must be an explicit boolean when set");
  }

  let html_sha: string | null = null;
  if (input.html_projection_sha != null) {
    if (typeof input.html_projection_sha !== "string") {
      throw new Error("html_projection_sha must be string or null");
    }
    const t = input.html_projection_sha.trim();
    html_sha = t || null;
  }

  const notes: string[] = [
    "purchase_executed=false — pure compose never charges",
    "hosted=false — pure compose never hosts bytes",
  ];

  // Free copy hit → free path (no purchase)
  if (free_copy_available === true) {
    notes.push("free_copy_available=true — path free_copy (purchase blocked)");
    const hostable = host_requested && html_sha !== null;
    if (hostable) {
      notes.push("HTML projection ready — hostable on free path");
    } else if (!html_sha) {
      notes.push("free path but html_projection_sha missing — hostable=false");
    }
    return {
      title,
      path: hostable ? "html_host" : "free_copy",
      free_copy_available: true,
      purchase_intent_allowed: false,
      purchase_executed: false,
      hostable,
      hosted: false,
      html_projection_sha: html_sha,
      notes,
      authority: "marketplace_book_host_compose_advisory",
    };
  }

  // Unknown free copy → incomplete (no invent miss)
  if (free_copy_available === null) {
    notes.push(
      "free_copy_available=null — path incomplete (no invent free miss)",
    );
    return {
      title,
      path: "incomplete",
      free_copy_available: null,
      purchase_intent_allowed: false,
      purchase_executed: false,
      hostable: false,
      hosted: false,
      html_projection_sha: html_sha,
      notes,
      authority: "marketplace_book_host_compose_advisory",
    };
  }

  // free_copy_available === false
  notes.push("free_copy_available=false — free miss");

  if (skip_free_copy && !operator_skip_acknowledged) {
    notes.push(
      "skip_free_copy without operator_skip_acknowledged — path blocked",
    );
    return {
      title,
      path: "blocked",
      free_copy_available: false,
      purchase_intent_allowed: false,
      purchase_executed: false,
      hostable: false,
      hosted: false,
      html_projection_sha: html_sha,
      notes,
      authority: "marketplace_book_host_compose_advisory",
    };
  }

  // Purchase intent: allowed after free miss (or skip with ack)
  let purchase_intent_allowed = true;
  if (
    input.purchase_intent_allowed !== undefined &&
    input.purchase_intent_allowed !== null
  ) {
    if (typeof input.purchase_intent_allowed !== "boolean") {
      throw new Error("purchase_intent_allowed must be boolean or null");
    }
    purchase_intent_allowed = input.purchase_intent_allowed;
  }
  notes.push(
    purchase_intent_allowed
      ? "purchase_intent_allowed=true (intent only, not executed)"
      : "purchase_intent_allowed=false",
  );

  if (!purchase_intent_allowed) {
    notes.push("purchase intent denied — path blocked");
    return {
      title,
      path: "blocked",
      free_copy_available: false,
      purchase_intent_allowed: false,
      purchase_executed: false,
      hostable: false,
      hosted: false,
      html_projection_sha: html_sha,
      notes,
      authority: "marketplace_book_host_compose_advisory",
    };
  }

  // After free miss: intent path; hostable only with ready HTML sha
  const hostable = host_requested && html_sha !== null;
  if (hostable) {
    notes.push(
      "purchase intent open + HTML projection ready — path html_host (still not hosted/purchased)",
    );
    return {
      title,
      path: "html_host",
      free_copy_available: false,
      purchase_intent_allowed: true,
      purchase_executed: false,
      hostable: true,
      hosted: false,
      html_projection_sha: html_sha,
      notes,
      authority: "marketplace_book_host_compose_advisory",
    };
  }

  notes.push(
    html_sha
      ? "host_requested=false — path purchase_intent"
      : "html_projection_sha missing — path purchase_intent (hostable=false)",
  );
  return {
    title,
    path: "purchase_intent",
    free_copy_available: false,
    purchase_intent_allowed: true,
    purchase_executed: false,
    hostable: false,
    hosted: false,
    html_projection_sha: html_sha,
    notes,
    authority: "marketplace_book_host_compose_advisory",
  };
}

export function formatMarketplaceComposeSummary(
  d: MarketplaceBookHostComposeDecision,
): string {
  return (
    `title=${d.title} · path=${d.path} · purchase_executed=false · hosted=false`
  );
}
