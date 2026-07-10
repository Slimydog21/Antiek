/**
 * Residual (ars): pure L5 offline purchase+host receipt readiness.
 *
 * Manual receipt token gates purchase+host (never invents charge / live rails).
 * Demo default tokens are honest flags — operators should replace for real orders.
 * Live payment rails remain dual-gate L5 deferred.
 */

export const MARKETPLACE_DEMO_RECEIPT_DEFAULT = "manual-order-token-demo";

export type MarketplaceReceiptReadiness = {
  receipt_trimmed: string;
  receipt_ready: boolean;
  is_demo_default: boolean;
  live_checkout_deferred: true;
  never_invent_charge: true;
  summary: string;
};

export function marketplaceReceiptReadiness(opts: {
  receiptRef?: string | null;
  /** When omitted, MARKETPLACE_DEMO_RECEIPT_DEFAULT is used for demo detection. */
  demoDefault?: string | null;
}): MarketplaceReceiptReadiness {
  const receipt_trimmed = String(opts.receiptRef || "").trim();
  const demo =
    String(opts.demoDefault || "").trim() || MARKETPLACE_DEMO_RECEIPT_DEFAULT;
  const receipt_ready = receipt_trimmed.length > 0;
  const is_demo_default = receipt_ready && receipt_trimmed === demo;

  let summary: string;
  if (!receipt_ready) {
    summary =
      "enter receipt token to enable Purchase + host · L5 live checkout deferred · never invent charge";
  } else if (is_demo_default) {
    summary =
      "receipt ready (demo default) · replace token for real orders · L5 live deferred · never invent charge";
  } else {
    summary =
      "receipt ready · purchase+host enabled · L5 live deferred · never invent charge";
  }

  return {
    receipt_trimmed,
    receipt_ready,
    is_demo_default,
    live_checkout_deferred: true,
    never_invent_charge: true,
    summary,
  };
}
