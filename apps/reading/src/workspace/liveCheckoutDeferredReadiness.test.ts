import { describe, expect, it } from "vitest";
import { liveCheckoutDeferredReadiness } from "./liveCheckoutDeferredReadiness";

describe("liveCheckoutDeferredReadiness (auy)", () => {
  it("is deferred offline by default", () => {
    const r = liveCheckoutDeferredReadiness({ book_id: "buy-modern" });
    expect(r.checkout_ready).toBe(false);
    expect(r.live_checkout_deferred).toBe(true);
    expect(r.block_reason).toBe("both_deferred");
    expect(r.never_invent_charge).toBe(true);
    expect(r.html_first).toBe(true);
    expect(r.dual_gate).toBe("L5");
    expect(r.payment_rails).toBe("manual_receipt_only");
    expect(r.checkout_label).toMatch(/L5 deferred/i);
    expect(r.checkout_title).toMatch(/never invent charge/i);
    expect(r.payment_adapter_env).toBe("ANTIEK_MARKETPLACE_LIVE_PAYMENT");
  });

  it("is deferred when dual-gate off even if upstream claims ready", () => {
    const r = liveCheckoutDeferredReadiness({
      dual_gate_enabled: false,
      live_upstream_ready: true,
    });
    expect(r.checkout_ready).toBe(false);
    expect(r.block_reason).toBe("dual_gate_off");
  });

  it("is deferred when dual-gate on but upstream not ready", () => {
    const r = liveCheckoutDeferredReadiness({
      dual_gate_enabled: true,
      live_upstream_ready: false,
    });
    expect(r.checkout_ready).toBe(false);
    expect(r.block_reason).toBe("upstream_not_ready");
    expect(r.summary).toMatch(/upstream not ready/i);
  });

  it("is checkout_ready only when dual-gate and upstream both ready", () => {
    const r = liveCheckoutDeferredReadiness({
      dual_gate_enabled: true,
      live_upstream_ready: true,
      book_id: "  paid-book  ",
    });
    expect(r.checkout_ready).toBe(true);
    expect(r.live_checkout_deferred).toBe(false);
    expect(r.block_reason).toBe("ok");
    expect(r.book_id).toBe("paid-book");
    expect(r.payment_rails).toBe("live_dual_gate");
    expect(r.checkout_label).toBe("Live checkout");
    expect(r.never_invent_charge).toBe(true);
  });
});
