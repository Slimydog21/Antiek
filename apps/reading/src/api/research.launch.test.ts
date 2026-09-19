import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, API_BASE: "", apiFetch: (...args: unknown[]) => apiFetch(...args) };
});

import { getGatherStatus, getLaunchAttemptStatus, launchPlan, LaunchOutcomeUnknownError } from "./research";

const GATHER = {
  view_format: "html",
  product_panel: "research_gather_status",
  configured_mode: "stub",
  gather_mode: "contract_stub",
  network_retrieval: false,
  exa_key_installed: false,
  parallel_key_installed: false,
  legal_gate_bypassed: false,
  legal_policy: {
    schema_version: 1, policy_snapshot_sha256: "a".repeat(64), issuer_state: "configured",
    write_enforcement_version: 1, read_enforcement_version: 1,
    migration_state: "current", production_defensible: true, reason_code: null,
  },
  launch_ready: true,
  production_defensible: true,
  stub_requires_acknowledgment: true,
  reviewed_gather_plan: null,
  configuration_error: null,
  multi_source_execution_activated: false,
};

describe("launchPlan durable attempt transport", () => {
  beforeEach(() => apiFetch.mockReset());

  it("sends the exact attempt key and accepts the closed response envelope", async () => {
    apiFetch.mockResolvedValue(new Response(JSON.stringify({
      session_id: "session-1",
      researches: [{ investigation_id: "leaf-1", sub_question: "why", question_node_id: null }],
      aggregate_cap_usd: 1,
      gather_receipt: GATHER,
      driver_receipt: {
        research_tier: "deep",
        reviewed_primary_provider: "xiaomi",
        reviewed_primary_model: "mimo-v2.5-pro",
        why: "MiMo workhorse fallback",
        reasoning_projected_max_cost_usd: 0.25,
        candidate_rank: 2,
        availability_source: "boot_registered_providers",
      },
      idempotency_replayed: false,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    await expect(launchPlan("plan-1", {
      expected_gather_mode: "contract_stub",
      allow_contract_stub: true,
    }, "attempt-1")).resolves.toMatchObject({ session_id: "session-1" });
    expect(apiFetch).toHaveBeenCalledWith("/research/plans/plan-1/launch", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ "Idempotency-Key": "attempt-1" }),
    }));
  });

  it("fails closed on a malformed or additive launch response", async () => {
    apiFetch.mockResolvedValue(new Response(JSON.stringify({
      session_id: "session-forged",
      researches: [],
      aggregate_cap_usd: 1,
      gather_receipt: GATHER,
      idempotency_replayed: false,
      injected: true,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    await expect(launchPlan("plan-1", {
      expected_gather_mode: "contract_stub",
    }, "attempt-1")).rejects.toThrow("invalid cascade launch response");
  });

  it("raises a non-redispatchable typed unknown-outcome result", async () => {
    apiFetch.mockResolvedValue(new Response(JSON.stringify({
      detail: {
        code: "launch_outcome_unknown",
        message: "do not redispatch",
        session_id: "session-existing",
      },
    }), { status: 409, headers: { "Content-Type": "application/json" } }));
    const error = await launchPlan("plan-1", {
      expected_gather_mode: "contract_stub",
    }, "attempt-1").catch((caught) => caught);
    expect(error).toBeInstanceOf(LaunchOutcomeUnknownError);
    expect(error.sessionId).toBe("session-existing");
  });

  it("reads a closed durable attempt status without dispatching", async () => {
    apiFetch.mockResolvedValue(new Response(JSON.stringify({
      plan_id: "plan-1",
      session_id: "session-existing",
      state: "claimed",
      response_integrity: null,
      session_authority_present: true,
      launch_evidence_present: true,
      action: "inspect_session",
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    await expect(getLaunchAttemptStatus("plan-1", "attempt-1")).resolves.toMatchObject({
      action: "inspect_session",
    });
    expect(apiFetch).toHaveBeenCalledWith("/research/plans/plan-1/launch-attempt", {
      method: "GET",
      headers: { "Idempotency-Key": "attempt-1" },
    });
  });

  it("rejects malformed multi-source exposure arithmetic and configuration digests", async () => {
    apiFetch.mockResolvedValue(new Response(JSON.stringify({
      ...GATHER,
      configured_mode: "multi_source",
      gather_mode: "authorized_multi_source",
      network_retrieval: true,
      exa_key_installed: true,
      parallel_key_installed: true,
      launch_ready: false,
      stub_requires_acknowledgment: false,
      multi_source_execution_activated: false,
      reviewed_gather_plan: {
        fingerprint: "f".repeat(64), leaf_count: 2,
        per_leaf_max_results: 23, per_leaf_max_cost_micros: 15_000,
        launch_max_results: 45, launch_max_cost_micros: 30_000,
        sources: ["exa", "parallel", "arxiv", "substack"],
        source_configuration_sha256: {
          exa: "a".repeat(64), parallel: "b".repeat(64),
          arxiv: "c".repeat(64), substack: "invalid",
        },
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    await expect(getGatherStatus("plan-1")).rejects.toThrow("invalid gather readiness response");
  });
});
