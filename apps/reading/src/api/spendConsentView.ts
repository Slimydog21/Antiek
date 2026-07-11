/**
 * Midnight Oil spend consent receipt view parser (#821 contract).
 *
 * Pure display-side validation of public ConsentReceipt fields.
 * Does **not** verify HMAC signatures or hold signing keys.
 * Fail closed: all fields required with declared types; no invent.
 */

export interface ConsentReceiptView {
  receipt_id: string;
  operator_id: string;
  job_id: string;
  operation_id: string;
  config_hash: string;
  ceiling_cents: number;
  issued_at_ms: number;
  expires_at_ms: number;
  nonce: string;
  key_id: string;
  /** Explicit: this view never asserts signature validity. */
  signature_verified: false;
  authority: "display_only";
}

export function parseConsentReceiptView(body: unknown): ConsentReceiptView {
  if (!body || typeof body !== "object") {
    throw new Error("consent receipt view must be an object");
  }
  const o = body as Record<string, unknown>;
  const str = (field: string): string => {
    const v = o[field];
    if (typeof v !== "string" || !v.trim()) {
      throw new Error(`consent receipt rejected: ${field} must be non-empty string`);
    }
    return v.trim();
  };
  const intMs = (field: string): number => {
    const v = o[field];
    if (typeof v !== "number" || !Number.isFinite(v) || !Number.isInteger(v)) {
      throw new Error(`consent receipt rejected: ${field} must be finite integer`);
    }
    return v;
  };
  const ceiling = intMs("ceiling_cents");
  if (ceiling < 0) {
    throw new Error("consent receipt rejected: ceiling_cents must be nonnegative");
  }
  const issued = intMs("issued_at_ms");
  const expires = intMs("expires_at_ms");
  if (expires < issued) {
    throw new Error("consent receipt rejected: expires_at_ms < issued_at_ms");
  }
  // Reject forged signature_verified true on display path.
  if (o.signature_verified === true) {
    throw new Error(
      "consent receipt rejected: signature_verified=true not accepted by display-only view",
    );
  }
  return {
    receipt_id: str("receipt_id"),
    operator_id: str("operator_id"),
    job_id: str("job_id"),
    operation_id: str("operation_id"),
    config_hash: str("config_hash"),
    ceiling_cents: ceiling,
    issued_at_ms: issued,
    expires_at_ms: expires,
    nonce: str("nonce"),
    key_id: str("key_id"),
    signature_verified: false,
    authority: "display_only",
  };
}

export function formatConsentReceiptSummary(r: ConsentReceiptView): string {
  return (
    `receipt ${r.receipt_id.slice(0, 12)}… · job=${r.job_id} · ` +
    `ceiling ${r.ceiling_cents}¢ · sig_verified=${r.signature_verified}`
  );
}

export function isConsentExpired(
  r: ConsentReceiptView,
  nowMs: number,
): boolean {
  if (typeof nowMs !== "number" || !Number.isFinite(nowMs)) {
    throw new Error("nowMs must be a finite number");
  }
  return nowMs > r.expires_at_ms;
}
