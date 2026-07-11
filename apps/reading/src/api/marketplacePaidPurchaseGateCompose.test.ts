import { describe, expect, it } from "vitest";
import {
  composeMarketplacePaidPurchaseGate,
  formatMarketplacePaidPurchaseGateSummary,
} from "./marketplacePaidPurchaseGateCompose";

describe("composeMarketplacePaidPurchaseGate", () => {
  it("free path gate ready without purchase", () => {
    const c = composeMarketplacePaidPurchaseGate({
      title: "Scaling Laws",
      account_id: "acct-1",
      free_copy_available: true,
      free_html_projection_sha: "sha-free-1",
      port_requested: true,
      purchase_ack: false,
      list_price_usd: 12,
      approved_spend_usd: 20,
      remaining_budget_usd: 50,
      operator_ack: true,
    });
    expect(c.purchase_ready).toBe(false);
    expect(c.gate_ready).toBe(true);
    expect(c.free_port.path).toBe("prefer_free_html");
    expect(c.purchase_executed).toBe(false);
    expect(c.charge_executed).toBe(false);
    expect(c.hosted).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
    expect(formatMarketplacePaidPurchaseGateSummary(c)).toMatch(
      /purchase_executed=false/,
    );
    expect(formatMarketplacePaidPurchaseGateSummary(c)).toMatch(
      /charge_executed=false/,
    );
  });

  it("paid path purchase_ready and gate_ready with sha", () => {
    const c = composeMarketplacePaidPurchaseGate({
      title: "Deep Learning Book",
      account_id: "acct-1",
      free_copy_available: false,
      purchase_html_projection_sha: "sha-paid-1",
      port_requested: true,
      purchase_ack: true,
      list_price_usd: 15,
      approved_spend_usd: 20,
      remaining_budget_usd: 100,
      operator_ack: true,
    });
    expect(c.purchase_ready).toBe(true);
    expect(c.would_exceed_budget).toBe(false);
    expect(c.gate_ready).toBe(true);
    expect(c.free_port.path).toBe("purchase_then_port");
    expect(c.purchase_executed).toBe(false);
    expect(c.charge_executed).toBe(false);
    expect(c.hosted).toBe(false);
    expect(c.authority).toBe(
      "marketplace_paid_purchase_gate_compose_advisory",
    );
  });

  it("blocks when list exceeds remaining budget", () => {
    const c = composeMarketplacePaidPurchaseGate({
      title: "Expensive",
      account_id: "acct-1",
      free_copy_available: false,
      purchase_html_projection_sha: "sha-x",
      port_requested: true,
      purchase_ack: true,
      list_price_usd: 50,
      approved_spend_usd: 60,
      remaining_budget_usd: 10,
      operator_ack: true,
    });
    expect(c.would_exceed_budget).toBe(true);
    expect(c.purchase_ready).toBe(false);
    expect(c.gate_ready).toBe(false);
    expect(c.charge_executed).toBe(false);
  });

  it("blocks when approved spend below list", () => {
    const c = composeMarketplacePaidPurchaseGate({
      title: "T",
      account_id: "a",
      free_copy_available: false,
      purchase_ack: true,
      list_price_usd: 20,
      approved_spend_usd: 10,
      remaining_budget_usd: 100,
      port_requested: true,
      purchase_html_projection_sha: "sha",
      operator_ack: true,
    });
    expect(c.purchase_ready).toBe(false);
  });

  it("would_exceed null when remaining unknown", () => {
    const c = composeMarketplacePaidPurchaseGate({
      title: "T",
      account_id: "a",
      free_copy_available: false,
      purchase_ack: true,
      list_price_usd: 10,
      approved_spend_usd: 20,
      remaining_budget_usd: null,
      port_requested: true,
      operator_ack: true,
    });
    expect(c.would_exceed_budget).toBeNull();
    expect(c.purchase_ready).toBe(false);
  });

  it("rejects free unknown for paid readiness", () => {
    const c = composeMarketplacePaidPurchaseGate({
      title: "T",
      account_id: "a",
      free_copy_available: null,
      purchase_ack: true,
      list_price_usd: 10,
      approved_spend_usd: 20,
      remaining_budget_usd: 50,
      port_requested: true,
      operator_ack: true,
    });
    expect(c.purchase_ready).toBe(false);
    expect(c.free_port.path).toBe("blocked_unknown_free");
  });
});
