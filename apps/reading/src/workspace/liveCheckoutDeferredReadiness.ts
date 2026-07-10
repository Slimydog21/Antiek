/**
 * Residual (auy): pure L5 live-checkout CTA readiness (digital book seamless port).
 *
 * Live payment rails are dual-gate L5 deferred. Offline default: checkout never
 * ready. checkout_ready only when operator dual-gate env is on AND live
 * payment upstream is ready — never invents charge or entitlement.
 *
 * Manual receipt path (marketplaceReceiptReadiness) remains the active offline
 * purchase+host path. HTML-first host view forever (PDF is ingest only).
 */

export type LiveCheckoutDeferredBlockReason =
  | "ok"
  | "dual_gate_off"
  | "upstream_not_ready"
  | "both_deferred";

export type LiveCheckoutDeferredReadiness = {
  dual_gate_enabled: boolean;
  live_upstream_ready: boolean;
  book_id: string;
  /** True only when dual-gate + upstream both ready — rare offline. */
  checkout_ready: boolean;
  block_reason: LiveCheckoutDeferredBlockReason;
  live_checkout_deferred: boolean;
  never_invent_charge: true;
  html_first: true;
  dual_gate: "L5";
  payment_rails: "manual_receipt_only" | "live_dual_gate";
  payment_adapter_sprint: "1";
  payment_adapter_boundary: "shipped_offline";
  payment_adapter_env: "ANTIEK_MARKETPLACE_LIVE_PAYMENT";
  summary: string;
  checkout_title: string;
  checkout_label: string;
};

/**
 * Live checkout CTA readiness for paid catalog rows.
 * Offline-honest: both gates default false → deferred forever until operator unlock.
 */
export function liveCheckoutDeferredReadiness(opts: {
  dual_gate_enabled?: boolean | null;
  live_upstream_ready?: boolean | null;
  book_id?: string | null;
}): LiveCheckoutDeferredReadiness {
  const dual_gate_enabled = opts.dual_gate_enabled === true;
  const live_upstream_ready = opts.live_upstream_ready === true;
  const book_id = String(opts.book_id || "").trim();

  let block_reason: LiveCheckoutDeferredBlockReason = "ok";
  if (!dual_gate_enabled && !live_upstream_ready) {
    block_reason = "both_deferred";
  } else if (!dual_gate_enabled) {
    block_reason = "dual_gate_off";
  } else if (!live_upstream_ready) {
    block_reason = "upstream_not_ready";
  }

  const checkout_ready = block_reason === "ok";
  const live_checkout_deferred = !checkout_ready;

  let summary: string;
  let checkout_title: string;
  let checkout_label: string;
  if (checkout_ready) {
    summary =
      "live checkout ready · dual-gate on · upstream ready · never invent charge · HTML host";
    checkout_title =
      "Live checkout enabled (L5 dual-gate · charged upstream required · HTML account port)";
    checkout_label = "Live checkout";
  } else if (block_reason === "dual_gate_off") {
    summary =
      "live checkout deferred · dual-gate ANTIEK_MARKETPLACE_LIVE_PAYMENT off · use manual receipt";
    checkout_title =
      "Live checkout deferred (L5 dual-gate ANTIEK_MARKETPLACE_LIVE_PAYMENT · Sprint 1–2 offline · never invent charge)";
    checkout_label = "Live checkout (L5 deferred)";
  } else if (block_reason === "upstream_not_ready") {
    summary =
      "live checkout deferred · dual-gate on but payment upstream not ready · never invent charge";
    checkout_title =
      "Live checkout deferred (payment upstream not ready · never invent charge · HTML host when live)";
    checkout_label = "Live checkout (L5 deferred)";
  } else {
    summary =
      "live checkout deferred · dual-gate off · upstream not ready · manual receipt only · never invent charge";
    checkout_title =
      "Live checkout deferred (L5 dual-gate ANTIEK_MARKETPLACE_LIVE_PAYMENT · Sprint 1–2 offline · never invent charge)";
    checkout_label = "Live checkout (L5 deferred)";
  }

  return {
    dual_gate_enabled,
    live_upstream_ready,
    book_id,
    checkout_ready,
    block_reason,
    live_checkout_deferred,
    never_invent_charge: true,
    html_first: true,
    dual_gate: "L5",
    payment_rails: checkout_ready ? "live_dual_gate" : "manual_receipt_only",
    payment_adapter_sprint: "1",
    payment_adapter_boundary: "shipped_offline",
    payment_adapter_env: "ANTIEK_MARKETPLACE_LIVE_PAYMENT",
    summary,
    checkout_title,
    checkout_label,
  };
}
