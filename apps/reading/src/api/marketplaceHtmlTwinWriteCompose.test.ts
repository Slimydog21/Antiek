import { describe, expect, it } from "vitest";
import {
  composeMarketplaceHtmlTwinWrite,
  formatMarketplaceHtmlTwinWriteSummary,
} from "./marketplaceHtmlTwinWriteCompose";

describe("composeMarketplaceHtmlTwinWrite", () => {
  it("free HTML book + twin + write ready", () => {
    const c = composeMarketplaceHtmlTwinWrite({
      session_id: "sess-1",
      asset_id: "book-1",
      draft_id: "draft-1",
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
        {
          source_id: "i1",
          body: "Power-law scaling holds in compute-optimal regimes",
          kind: "insight",
        },
      ],
      mark_for_prompt_context: true,
    });
    expect(c.market_twin.session_ready).toBe(true);
    expect(c.write_pack.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.purchase_executed).toBe(false);
    expect(c.charge_executed).toBe(false);
    expect(c.hosted).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.draft_written).toBe(false);
    expect(c.analysis_written).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.authority).toBe("marketplace_html_twin_write_compose_advisory");
    expect(formatMarketplaceHtmlTwinWriteSummary(c)).toMatch(
      /pdf_view_authorized=false/,
    );
  });

  it("budget block prevents pack_ready", () => {
    const c = composeMarketplaceHtmlTwinWrite({
      session_id: "s",
      asset_id: "b",
      draft_id: "d",
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
    expect(c.market_twin.session_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.charge_executed).toBe(false);
  });

  it("operator_ack false blocks", () => {
    const c = composeMarketplaceHtmlTwinWrite({
      session_id: "sess-1",
      asset_id: "book-1",
      draft_id: "draft-1",
      title: "Scaling Laws",
      account_id: "acct-1",
      free_copy_available: true,
      free_html_projection_sha: "sha-free",
      port_requested: true,
      purchase_ack: false,
      list_price_usd: 10,
      approved_spend_usd: 20,
      remaining_budget_usd: 50,
      operator_ack: false,
      view_requested: true,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.draft_written).toBe(false);
  });

  it("caller twin_slices override", () => {
    const c = composeMarketplaceHtmlTwinWrite({
      session_id: "sess-1",
      asset_id: "book-1",
      draft_id: "draft-1",
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
      twin_slices: [
        {
          parent_asset_id: "book-1",
          insights: ["A", "B"],
          questions: ["Q?"],
        },
      ],
      chase_slots: [
        {
          slot_id: "s1",
          question_id: "q1",
          parent_asset_id: "book-1",
          status: "completed",
          findings: ["f1"],
        },
        {
          slot_id: "s2",
          question_id: "q2",
          parent_asset_id: "book-1",
          status: "completed",
          findings: ["f2"],
        },
      ],
      analysis_kind: "full_analysis",
    });
    expect(c.write_pack.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.merge_executed).toBe(false);
  });
});
