import { describe, expect, it } from "vitest";
import {
  formatConsentReceiptSummary,
  isConsentExpired,
  parseConsentReceiptView,
} from "./spendConsentView";

const sample = {
  receipt_id: "rcpt-abcdef123456",
  operator_id: "op-1",
  job_id: "job-1",
  operation_id: "opn-1",
  config_hash: "abc123",
  ceiling_cents: 500,
  issued_at_ms: 1_000,
  expires_at_ms: 2_000,
  nonce: "n1",
  key_id: "k1",
};

describe("parseConsentReceiptView", () => {
  it("parses and forces display_only", () => {
    const r = parseConsentReceiptView(sample);
    expect(r.signature_verified).toBe(false);
    expect(r.authority).toBe("display_only");
    expect(r.ceiling_cents).toBe(500);
  });

  it("rejects missing fields and forged signature_verified", () => {
    expect(() => parseConsentReceiptView({ ...sample, receipt_id: "" })).toThrow(
      /receipt_id/,
    );
    expect(() =>
      parseConsentReceiptView({ ...sample, signature_verified: true }),
    ).toThrow(/signature_verified/);
  });

  it("rejects expires before issued", () => {
    expect(() =>
      parseConsentReceiptView({
        ...sample,
        issued_at_ms: 5_000,
        expires_at_ms: 1_000,
      }),
    ).toThrow(/expires_at_ms/);
  });
});

describe("isConsentExpired / format", () => {
  it("expiry and summary", () => {
    const r = parseConsentReceiptView(sample);
    expect(isConsentExpired(r, 1_500)).toBe(false);
    expect(isConsentExpired(r, 2_000)).toBe(true); // exact expiry is expired
    expect(isConsentExpired(r, 2_001)).toBe(true);
    expect(formatConsentReceiptSummary(r)).toMatch(/ceiling 500/);
  });
});
