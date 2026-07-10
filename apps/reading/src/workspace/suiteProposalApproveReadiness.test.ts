import { describe, expect, it } from "vitest";
import { suiteProposalApproveReadiness } from "./suiteProposalApproveReadiness";

describe("suiteProposalApproveReadiness (aux)", () => {
  it("is not approve_ready without proposal", () => {
    const r = suiteProposalApproveReadiness({});
    expect(r.approve_ready).toBe(false);
    expect(r.reject_ready).toBe(false);
    expect(r.block_reason).toBe("no_proposal");
    expect(r.propose_neq_promote).toBe(true);
    expect(r.never_auto_promote).toBe(true);
    expect(r.approve_title).toMatch(/No suite proposal/i);
  });

  it("is not approve_ready without proposal_id", () => {
    const r = suiteProposalApproveReadiness({
      has_proposal: true,
      status: "proposed",
    });
    expect(r.approve_ready).toBe(false);
    expect(r.block_reason).toBe("no_proposal_id");
    expect(r.approve_title).toMatch(/proposal_id/i);
  });

  it("is not approve_ready when status is not proposed", () => {
    const r = suiteProposalApproveReadiness({
      has_proposal: true,
      proposal_id: "prop_abc",
      status: "promoted",
    });
    expect(r.approve_ready).toBe(false);
    expect(r.block_reason).toBe("not_proposed_status");
    expect(r.approve_title).toMatch(/not in proposed status/i);
  });

  it("refuses when auto_promoted is true", () => {
    const r = suiteProposalApproveReadiness({
      has_proposal: true,
      proposal_id: "prop_evil",
      status: "proposed",
      auto_promoted: true,
    });
    expect(r.approve_ready).toBe(false);
    expect(r.block_reason).toBe("auto_promoted_refused");
    expect(r.approve_title).toMatch(/auto_promoted/i);
    expect(r.never_auto_promote).toBe(true);
  });

  it("is approve_ready for proposed proposal with id", () => {
    const r = suiteProposalApproveReadiness({
      has_proposal: true,
      proposal_id: "  prop_testdeadbeef01  ",
      status: "proposed",
      auto_promoted: false,
    });
    expect(r.approve_ready).toBe(true);
    expect(r.reject_ready).toBe(true);
    expect(r.block_reason).toBe("ok");
    expect(r.proposal_id).toBe("prop_testdeadbeef01");
    expect(r.summary).toMatch(/propose≠promote/);
    expect(r.approve_title).toMatch(/never auto-promote/i);
    expect(r.reject_title).toMatch(/active suite unchanged/i);
  });

  it("infers has_proposal from proposal_id alone", () => {
    const r = suiteProposalApproveReadiness({
      proposal_id: "prop_x",
      status: "proposed",
    });
    expect(r.has_proposal).toBe(true);
    expect(r.approve_ready).toBe(true);
  });
});
