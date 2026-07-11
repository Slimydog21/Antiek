import { describe, expect, it } from "vitest";
import {
  composePaidPurchaseHtmlViewSession,
  formatPaidPurchaseHtmlViewSessionSummary,
} from "./paidPurchaseHtmlViewSessionCompose";

describe("composePaidPurchaseHtmlViewSession", () => {
  it("free path opens HTML session package", () => {
    const c = composePaidPurchaseHtmlViewSession({
      session_id: "sess-1",
      asset_id: "book-1",
      title: "Scaling Laws",
      account_id: "acct-1",
      free_copy_available: true,
      free_html_projection_sha: "sha-free",
      port_requested: true,
      purchase_ack: false,
      list_price_usd: 10,
      approved_spend_usd: 20,
      remaining_budget_usd: 50,
      operator_ack: true,
      view_requested: true,
      twin_bound: true,
    });
    expect(c.purchase_gate.gate_ready).toBe(true);
    expect(c.view?.html_view_ready).toBe(true);
    expect(c.session_package_ready).toBe(true);
    expect(c.purchase_executed).toBe(false);
    expect(c.charge_executed).toBe(false);
    expect(c.hosted).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(formatPaidPurchaseHtmlViewSessionSummary(c)).toMatch(
      /pdf_view_authorized=false/,
    );
  });

  it("paid path with sha ready", () => {
    const c = composePaidPurchaseHtmlViewSession({
      session_id: "sess-2",
      asset_id: "book-2",
      title: "Deep Learning",
      account_id: "acct-1",
      free_copy_available: false,
      purchase_html_projection_sha: "sha-paid",
      port_requested: true,
      purchase_ack: true,
      list_price_usd: 15,
      approved_spend_usd: 20,
      remaining_budget_usd: 100,
      operator_ack: true,
      view_requested: true,
    });
    expect(c.purchase_gate.purchase_ready).toBe(true);
    expect(c.session_package_ready).toBe(true);
    expect(c.charge_executed).toBe(false);
    expect(c.authority).toBe(
      "paid_purchase_html_view_session_compose_advisory",
    );
  });

  it("budget block prevents package ready", () => {
    const c = composePaidPurchaseHtmlViewSession({
      session_id: "s",
      asset_id: "b",
      title: "Expensive",
      account_id: "a",
      free_copy_available: false,
      purchase_html_projection_sha: "sha",
      port_requested: true,
      purchase_ack: true,
      list_price_usd: 50,
      approved_spend_usd: 60,
      remaining_budget_usd: 5,
      operator_ack: true,
      view_requested: true,
    });
    expect(c.purchase_gate.purchase_ready).toBe(false);
    expect(c.session_package_ready).toBe(false);
    expect(c.purchase_executed).toBe(false);
  });

  it("pdf claimed format blocks session_package_ready", () => {
    const c = composePaidPurchaseHtmlViewSession({
      session_id: "s",
      asset_id: "b",
      title: "T",
      account_id: "a",
      free_copy_available: true,
      free_html_projection_sha: "sha",
      port_requested: true,
      purchase_ack: false,
      list_price_usd: null,
      approved_spend_usd: null,
      remaining_budget_usd: null,
      operator_ack: true,
      view_requested: true,
      claimed_format: "pdf",
    });
    expect(c.view?.html_view_ready).toBe(false);
    expect(c.session_package_ready).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
  });
});
