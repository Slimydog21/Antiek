import { describe, expect, it } from "vitest";

import {
  MARKETPLACE_DEMO_RECEIPT_DEFAULT,
  marketplaceReceiptReadiness,
} from "./marketplaceReceiptReadiness";

describe("marketplaceReceiptReadiness residual (ars)", () => {
  it("is not ready when receipt empty", () => {
    const r = marketplaceReceiptReadiness({});
    expect(r.receipt_ready).toBe(false);
    expect(r.is_demo_default).toBe(false);
    expect(r.live_checkout_deferred).toBe(true);
    expect(r.never_invent_charge).toBe(true);
    expect(r.summary).toMatch(/enter receipt token/i);
  });

  it("flags demo default honestly", () => {
    const r = marketplaceReceiptReadiness({
      receiptRef: MARKETPLACE_DEMO_RECEIPT_DEFAULT,
    });
    expect(r.receipt_ready).toBe(true);
    expect(r.is_demo_default).toBe(true);
    expect(r.summary).toMatch(/demo default/i);
    expect(r.summary).toMatch(/never invent charge/i);
  });

  it("accepts non-demo receipt without inventing live rails", () => {
    const r = marketplaceReceiptReadiness({
      receiptRef: "  order-real-42  ",
    });
    expect(r.receipt_trimmed).toBe("order-real-42");
    expect(r.receipt_ready).toBe(true);
    expect(r.is_demo_default).toBe(false);
    expect(r.live_checkout_deferred).toBe(true);
    expect(r.summary).toMatch(/purchase\+host enabled/i);
  });

  it("allows custom demoDefault token", () => {
    const r = marketplaceReceiptReadiness({
      receiptRef: "custom-demo",
      demoDefault: "custom-demo",
    });
    expect(r.is_demo_default).toBe(true);
  });
});
