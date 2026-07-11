import { describe, expect, it } from "vitest";
import {
  composeMarketplaceHtmlViewTwinSession,
  formatMarketplaceHtmlViewTwinSessionSummary,
} from "./marketplaceHtmlViewTwinSessionCompose";

describe("composeMarketplaceHtmlViewTwinSession", () => {
  it("free path HTML session + twin ready", () => {
    const c = composeMarketplaceHtmlViewTwinSession({
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
      twin_findings: [
        {
          source_id: "q1",
          body: "What is the core thesis?",
          kind: "question",
        },
      ],
      mark_for_prompt_context: true,
    });
    expect(c.market_view.session_package_ready).toBe(true);
    expect(c.twin_feed?.feed_ready).toBe(true);
    expect(c.session_ready).toBe(true);
    expect(c.purchase_executed).toBe(false);
    expect(c.charge_executed).toBe(false);
    expect(c.hosted).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.record_persisted).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.authority).toBe(
      "marketplace_html_view_twin_session_compose_advisory",
    );
    expect(formatMarketplaceHtmlViewTwinSessionSummary(c)).toMatch(
      /pdf_view_authorized=false/,
    );
  });

  it("paid path ready with twin", () => {
    const c = composeMarketplaceHtmlViewTwinSession({
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
    expect(c.market_view.purchase_gate.purchase_ready).toBe(true);
    expect(c.session_ready).toBe(true);
    expect(c.charge_executed).toBe(false);
  });

  it("budget block prevents session_ready", () => {
    const c = composeMarketplaceHtmlViewTwinSession({
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
    expect(c.market_view.session_package_ready).toBe(false);
    expect(c.session_ready).toBe(false);
    expect(c.purchase_executed).toBe(false);
  });

  it("skip twin still ready when market ready", () => {
    const c = composeMarketplaceHtmlViewTwinSession({
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
      include_twin_feed: false,
    });
    expect(c.twin_feed).toBeNull();
    expect(c.session_ready).toBe(true);
  });

  it("pdf claim blocks market package", () => {
    const c = composeMarketplaceHtmlViewTwinSession({
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
    expect(c.market_view.session_package_ready).toBe(false);
    expect(c.session_ready).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
  });
});
