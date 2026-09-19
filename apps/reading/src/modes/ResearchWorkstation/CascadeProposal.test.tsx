/**
 * CascadeProposal.test.tsx — the Research door's cascade mode (SPR-01
 * product-depth, milestones 1, 2, 4).
 *
 * Pins the behaviour: choosing "break into sub-questions" POSTs the problem
 * and renders the proposed sub-questions inline (M1); each sub-question can be
 * trimmed/edited through the SPR-05 edit contract and launch approves-then-
 * launches the gated plan (M2); and when the propose call fails — the common
 * no-provider-keys case — the SAME shared <AIActionFailure> is shown, never a
 * fake tree or a stuck spinner (M4).
 *
 * The cascade API is mocked at the module boundary so this is a true unit of
 * the door: we assert it calls the sanctioned createPlan / editPlan /
 * approvePlan / launchPlan (never reimplements them) and shows only human
 * words (no "leaf", "investigation", raw ids).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { CreatePlanResponse, PlanResponse } from "../../api/research";

const {
  createPlanMock,
  editPlanMock,
  approvePlanMock,
  launchPlanMock,
  getLaunchAttemptStatusMock,
  getBudgetDefaultsMock,
  getGatherStatusMock,
  getCascadeDriverReadinessMock,
  listLegalPolicyDispatchLeasesMock,
  recoverLegalPolicyDispatchLeaseMock,
} = vi.hoisted(() => ({
  createPlanMock: vi.fn(),
  editPlanMock: vi.fn(),
  approvePlanMock: vi.fn(),
  launchPlanMock: vi.fn(),
  getLaunchAttemptStatusMock: vi.fn(),
  getBudgetDefaultsMock: vi.fn(),
  getGatherStatusMock: vi.fn(),
  getCascadeDriverReadinessMock: vi.fn(),
  listLegalPolicyDispatchLeasesMock: vi.fn(),
  recoverLegalPolicyDispatchLeaseMock: vi.fn(),
}));

vi.mock("../../api/research", async (orig) => {
  const actual = await orig<typeof import("../../api/research")>();
  return {
    ...actual,
    createPlan: createPlanMock,
    editPlan: editPlanMock,
    approvePlan: approvePlanMock,
    launchPlan: launchPlanMock,
    getLaunchAttemptStatus: getLaunchAttemptStatusMock,
    getBudgetDefaults: getBudgetDefaultsMock,
    getGatherStatus: getGatherStatusMock,
    getCascadeDriverReadiness: getCascadeDriverReadinessMock,
    listLegalPolicyDispatchLeases: listLegalPolicyDispatchLeasesMock,
    recoverLegalPolicyDispatchLease: recoverLegalPolicyDispatchLeaseMock,
  };
});

vi.mock("../../components/engagement/DecisionTreeDriverBadge", () => ({
  DecisionTreeDriverBadge: ({ researchTier }: { researchTier: string }) => (
    <div data-testid="cascade-driver">Driver tier: {researchTier}</div>
  ),
}));
vi.mock("../../components/engagement/ResearchLaunchBudgetPanel", () => ({
  ResearchLaunchBudgetPanel: ({ researchTier, onResearchTierChange }: {
    researchTier: string;
    onResearchTierChange?: (tier: "wrestle") => void;
  }) => (
    <div data-testid="cascade-budget">Budget tier: {researchTier}
      <button onClick={() => onResearchTierChange?.("wrestle")}>Pick wrestle</button>
    </div>
  ),
}));

import CascadeProposal from "./CascadeProposal";

function planNode(local_id: string, question: string, children: never[] = []) {
  return {
    local_id,
    question,
    rationale: "",
    focus_boundary: "",
    budget_usd: null,
    max_depth: null,
    graph_node_id: `q-${local_id}`,
    children,
  };
}

const TREE = {
  root: planNode("pn-root", "How will the energy transition reshape geopolitics?", [
    planNode("pn-1", "Which states gain leverage from critical-mineral supply?") as never,
    planNode("pn-2", "How does cheap solar change petro-state economies?") as never,
    planNode("pn-3", "What new chokepoints replace oil shipping lanes?") as never,
  ]),
  seed_kind: "problem",
  seed_provenance: {},
  approval: { state: "draft" as const, approved_at: null, approved_by: null, plan_version: 1 },
  root_investigation_id: "__operator__",
};

const CREATE_RESP: CreatePlanResponse = {
  root_node_id: "q-pn-root",
  tree: TREE,
  capped_nodes: [],
  over_broad_leaves: [],
};

beforeEach(() => {
  sessionStorage.clear();
  createPlanMock.mockReset();
  editPlanMock.mockReset();
  approvePlanMock.mockReset();
  launchPlanMock.mockReset();
  getLaunchAttemptStatusMock.mockReset();
  getLaunchAttemptStatusMock.mockResolvedValue({
    plan_id: "q-pn-root",
    session_id: "session-unknown",
    state: "claimed",
    response_integrity: null,
    session_authority_present: true,
    launch_evidence_present: true,
    action: "inspect_session",
  });
  getBudgetDefaultsMock.mockReset();
  getGatherStatusMock.mockReset();
  listLegalPolicyDispatchLeasesMock.mockReset();
  recoverLegalPolicyDispatchLeaseMock.mockReset();
  getBudgetDefaultsMock.mockResolvedValue({ per_research_cost_usd: 0.5, per_research_max_steps: 50 });
  getGatherStatusMock.mockResolvedValue({
    view_format: "html", product_panel: "research_gather_status",
    configured_mode: "exa", gather_mode: "exa_reasoning", network_retrieval: true,
    exa_key_installed: true, legal_gate_bypassed: false, launch_ready: true,
    legal_policy: { schema_version: 1, policy_snapshot_sha256: "a".repeat(64), issuer_state: "configured", write_enforcement_version: 1, read_enforcement_version: 1, migration_state: "current", production_defensible: true, reason_code: null },
    production_defensible: true, stub_requires_acknowledgment: false,
  });
  getCascadeDriverReadinessMock.mockImplementation(async (researchTier: string) => ({
    research_tier: researchTier, ready: true, provider: "xiaomi", model: "mimo-v2.5-pro",
    candidate_rank: 2, availability_source: "boot_registered_providers",
    reason: "MiMo workhorse fallback",
  }));
  listLegalPolicyDispatchLeasesMock.mockResolvedValue({ count: 0, leases: [] });
  recoverLegalPolicyDispatchLeaseMock.mockResolvedValue({
    lease_id: "lease-1", recovered: true, idempotency_replayed: false,
  });
});
afterEach(() => cleanup());

function renderProposal(overrides: Partial<Parameters<typeof CascadeProposal>[0]> = {}) {
  const onLaunched = overrides.onLaunched ?? vi.fn();
  const onFallBackToAsk = overrides.onFallBackToAsk ?? vi.fn();
  render(
    <CascadeProposal
      problem="How will the energy transition reshape geopolitics?"
      onLaunched={onLaunched}
      onFallBackToAsk={onFallBackToAsk}
    />,
  );
  return { onLaunched, onFallBackToAsk };
}

describe("CascadeProposal — propose the sub-question tree (M1)", () => {
  it("POSTs the problem and renders the proposed sub-questions", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    renderProposal();
    await waitFor(() =>
      expect(createPlanMock).toHaveBeenCalledWith(
        expect.objectContaining({ problem: expect.stringMatching(/energy transition/i) }),
      ),
    );
    expect(await screen.findByText(/critical-mineral supply/i)).toBeTruthy();
    expect(screen.getByText(/petro-state economies/i)).toBeTruthy();
    expect(screen.getByText(/chokepoints replace oil/i)).toBeTruthy();
  });

  it("shows the real budget estimate read from the contract, not a hardcoded number", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    renderProposal();
    // 3 sub-questions × $0.50 default per-research cap = up to $1.50.
    expect(await screen.findByText(/estimated up to \$1\.50 for 3 researches/i)).toBeTruthy();
  });

  it("counts and renders the leaves the backend launches, not just the top level", async () => {
    // cascade_session launches one research per tree LEAF. A nested proposal
    // (pn-2 splits in two) has 4 leaves — pn-1, pn-2a, pn-2b, pn-3 — not the 3
    // top-level nodes. The door must show + count the 4 it will actually run, so
    // "Start N researches" can never understate what launches.
    createPlanMock.mockResolvedValue({
      ...CREATE_RESP,
      tree: {
        ...TREE,
        root: planNode("pn-root", "How will the energy transition reshape geopolitics?", [
          planNode("pn-1", "Which states gain leverage from critical-mineral supply?") as never,
          planNode("pn-2", "How does cheap solar change petro-state economies?", [
            planNode("pn-2a", "What happens to Gulf sovereign wealth funds?") as never,
            planNode("pn-2b", "Does domestic solar shift OPEC cohesion?") as never,
          ]) as never,
          planNode("pn-3", "What new chokepoints replace oil shipping lanes?") as never,
        ]),
      },
    });
    renderProposal();
    expect(await screen.findByText(/Gulf sovereign wealth funds/i)).toBeTruthy();
    expect(screen.getByText(/OPEC cohesion/i)).toBeTruthy();
    // The grouping node pn-2 is not itself a launchable leaf.
    expect(screen.queryByText(/petro-state economies/i)).toBeNull();
    expect(await screen.findByRole("button", { name: /Start 4 researches/i })).toBeTruthy();
  });

  it("leaks no substrate vocabulary into the rendered surface", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    const { container } = render(
      <CascadeProposal problem="P" onLaunched={vi.fn()} onFallBackToAsk={vi.fn()} />,
    );
    await screen.findByText(/critical-mineral supply/i);
    const dom = container.textContent ?? "";
    for (const banned of ["investigation_id", "leaf", "spawn", "decomposer", "cascade_planner", "pn-root"]) {
      expect(dom.toLowerCase()).not.toContain(banned.toLowerCase());
    }
  });
});

describe("CascadeProposal — trim + gated launch (M2)", () => {
  it("locks stub launch until the operator explicitly acknowledges no retrieval", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    getGatherStatusMock.mockResolvedValueOnce({
      view_format: "html", product_panel: "research_gather_status",
      configured_mode: "stub", gather_mode: "contract_stub", network_retrieval: false,
      exa_key_installed: false, legal_gate_bypassed: false, launch_ready: true,
      legal_policy: { schema_version: 1, policy_snapshot_sha256: null, issuer_state: "not_configured", write_enforcement_version: 1, read_enforcement_version: 1, migration_state: "current", production_defensible: false, reason_code: "global_policy_issuer_not_configured" },
      production_defensible: false, stub_requires_acknowledgment: true,
    });
    launchPlanMock.mockResolvedValue({ session_id: "session-stub" });
    renderProposal();
    const launch = await screen.findByRole("button", { name: /Start 3 researches/i });
    expect((launch as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("checkbox"));
    expect((launch as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(launch);
    await waitFor(() => expect(launchPlanMock).toHaveBeenCalledWith("q-pn-root", {
      expected_gather_mode: "contract_stub", allow_contract_stub: true, research_tier: "deep",
    }, expect.any(String)));
  });

  it("fails closed when gather readiness is malformed", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    // getGatherStatus performs runtime validation centrally; malformed JSON is
    // exposed to consumers as a rejected readiness request.
    getGatherStatusMock.mockRejectedValueOnce(new Error("invalid gather readiness response"));
    renderProposal();
    await screen.findByText(/could not be verified/i);
    expect((screen.getByRole("button", { name: /Start 3 researches/i }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("removes a sub-question through the SPR-05 edit contract", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    const reduced: PlanResponse = {
      root_node_id: "q-pn-root",
      tree: { ...TREE, root: { ...TREE.root, children: TREE.root.children.slice(0, 2) } },
      launchable: false,
    };
    editPlanMock.mockResolvedValue(reduced);
    renderProposal();
    await screen.findByText(/chokepoints replace oil/i);
    // Remove the third sub-question.
    fireEvent.click(screen.getAllByRole("button", { name: "remove" })[2]);
    await waitFor(() =>
      expect(editPlanMock).toHaveBeenCalledWith(
        "q-pn-root",
        expect.objectContaining({ op: "remove", target_local_id: "pn-3" }),
      ),
    );
    await waitFor(() => expect(screen.queryByText(/chokepoints replace oil/i)).toBeNull());
  });

  it("launch approves then launches the plan and hands back the session", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    approvePlanMock.mockResolvedValue({
      root_node_id: "q-pn-root",
      approval: { state: "approved", approved_at: "t", approved_by: "x", plan_version: 1 },
      launchable: true,
    });
    launchPlanMock.mockResolvedValue({
      session_id: "session-q-pn-root",
      researches: [],
      aggregate_cap_usd: 10,
    });
    const { onLaunched } = renderProposal();
    const launch = await screen.findByRole("button", { name: /Start 3 researches/i });
    fireEvent.click(launch);
    await waitFor(() => expect(approvePlanMock).toHaveBeenCalledWith("q-pn-root"));
    await waitFor(() => expect(launchPlanMock).toHaveBeenCalledWith("q-pn-root", {
      expected_gather_mode: "exa_reasoning",
      allow_contract_stub: false,
      research_tier: "deep",
    }, expect.any(String)));
    await waitFor(() => expect(onLaunched).toHaveBeenCalledWith("session-q-pn-root"));
  });

  it("launches the newly reviewed tier rather than a stale callback tier", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    approvePlanMock.mockResolvedValue({ launchable: true });
    launchPlanMock.mockResolvedValue({ session_id: "session-wrestle" });
    renderProposal();
    await screen.findByRole("button", { name: /Start 3 researches/i });
    fireEvent.click(screen.getByRole("button", { name: "Pick wrestle" }));
    await waitFor(() => expect(
      (screen.getByRole("button", { name: /Start 3 researches/i }) as HTMLButtonElement).disabled,
    ).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: /Start 3 researches/i }));
    await waitFor(() => expect(launchPlanMock).toHaveBeenCalledWith(
      "q-pn-root",
      expect.objectContaining({ research_tier: "wrestle" }),
      expect.any(String),
    ));
  });

  it("retries an ambiguous launch with the same durable attempt key", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    approvePlanMock.mockResolvedValue({
      root_node_id: "q-pn-root",
      approval: { state: "approved", approved_at: "t", approved_by: "x", plan_version: 1 },
      launchable: true,
    });
    launchPlanMock
      .mockRejectedValueOnce(new Error("response lost"))
      .mockResolvedValueOnce({ session_id: "recovered-session" });
    const { onLaunched } = renderProposal();
    fireEvent.click(await screen.findByRole("button", { name: /Start 3 researches/i }));
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    await waitFor(() => expect(launchPlanMock).toHaveBeenCalledTimes(2));
    const firstKey = launchPlanMock.mock.calls[0][2];
    const retryKey = launchPlanMock.mock.calls[1][2];
    expect(firstKey).toEqual(expect.any(String));
    expect(retryKey).toBe(firstKey);
    expect(approvePlanMock).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(onLaunched).toHaveBeenCalledWith("recovered-session"));
  });

  it("cannot edit or rotate authority while a launch is in flight", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    approvePlanMock.mockResolvedValue({ launchable: true });
    let finishLaunch: ((value: { session_id: string }) => void) | undefined;
    launchPlanMock.mockImplementation(() => new Promise((resolve) => {
      finishLaunch = resolve;
    }));
    renderProposal();
    fireEvent.click(await screen.findByRole("button", { name: /Start 3 researches/i }));
    await waitFor(() => expect(launchPlanMock).toHaveBeenCalledTimes(1));
    const key = launchPlanMock.mock.calls[0][2];
    const removeButtons = screen.getAllByRole("button", { name: "remove" });
    expect(removeButtons.every((button) => (button as HTMLButtonElement).disabled)).toBe(true);
    fireEvent.click(removeButtons[0]);
    expect(editPlanMock).not.toHaveBeenCalled();
    expect(launchPlanMock.mock.calls[0][2]).toBe(key);
    finishLaunch?.({ session_id: "session-in-flight" });
  });

  it("never redispatches an unknown launch and offers the existing session", async () => {
    const { LaunchOutcomeUnknownError } = await import("../../api/research");
    createPlanMock.mockResolvedValue(CREATE_RESP);
    approvePlanMock.mockResolvedValue({ launchable: true });
    launchPlanMock.mockRejectedValue(new LaunchOutcomeUnknownError("session-unknown"));
    const { onLaunched } = renderProposal();
    fireEvent.click(await screen.findByRole("button", { name: /Start 3 researches/i }));
    const inspect = await screen.findByRole("button", { name: "Inspect existing session" });
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    expect(launchPlanMock).toHaveBeenCalledTimes(1);
    fireEvent.click(inspect);
    expect(onLaunched).toHaveBeenCalledWith("session-unknown");
    expect(launchPlanMock).toHaveBeenCalledTimes(1);
  });
});

describe("CascadeProposal — renders the planner's REAL output, no placeholders (SPR-05 M2 honesty)", () => {
  it("shows each sub-question's planner RATIONALE when present", async () => {
    createPlanMock.mockResolvedValue({
      ...CREATE_RESP,
      tree: {
        ...TREE,
        root: planNode("pn-root", "How will the energy transition reshape geopolitics?", [
          {
            ...planNode("pn-1", "Which states gain leverage from critical-mineral supply?"),
            rationale: "Lithium and cobalt concentration is the new oil map.",
          } as never,
        ]),
      },
    });
    renderProposal();
    // The question AND its real rationale (the planner's "why") both render.
    expect(await screen.findByText(/critical-mineral supply/i)).toBeTruthy();
    expect(screen.getByText(/Lithium and cobalt concentration is the new oil map/i)).toBeTruthy();
  });

  it("does NOT fabricate 'known insights' / 'open questions' blocks the planner never produced", async () => {
    // The planner returns ONLY sub-questions (its real output). The surface
    // must not paint hand-faked insight/open-question sections to match the
    // sprint prose — it names that gap in code/handoff instead (rigor #1).
    createPlanMock.mockResolvedValue(CREATE_RESP);
    renderProposal();
    await screen.findByText(/critical-mineral supply/i);
    const dom = (document.body.textContent ?? "").toLowerCase();
    // No fabricated section headers for artifacts that don't exist pre-run.
    expect(dom).not.toContain("known insights");
    expect(dom).not.toContain("open questions");
    // What IS shown is the honest sub-question framing.
    expect(screen.getByText(/Proposed sub-questions/i)).toBeTruthy();
  });

  it("an edited-then-approved plan launches (the edit re-opens the gate, launch runs the current tree)", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    // Editing returns a fresh tree with launchable reset — the gate re-opens.
    editPlanMock.mockResolvedValue({
      root_node_id: "q-pn-root",
      tree: {
        ...TREE,
        root: {
          ...TREE.root,
          children: [
            { ...(TREE.root.children[0] as object), question: "Reworded: who controls the minerals?" } as never,
            ...TREE.root.children.slice(1),
          ],
        },
      },
      launchable: false,
    });
    approvePlanMock.mockResolvedValue({
      root_node_id: "q-pn-root",
      approval: { state: "approved", approved_at: "t", approved_by: "x", plan_version: 2 },
      launchable: true,
    });
    launchPlanMock.mockResolvedValue({ session_id: "sess-edited", researches: [], aggregate_cap_usd: 10 });
    const { onLaunched } = renderProposal();
    await screen.findByText(/critical-mineral supply/i);
    // Reword the first sub-question through the edit contract.
    fireEvent.click(screen.getAllByRole("button", { name: "edit" })[0]);
    const input = screen.getByLabelText("Edit sub-question");
    fireEvent.change(input, { target: { value: "Reworded: who controls the minerals?" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(editPlanMock).toHaveBeenCalledWith(
        "q-pn-root",
        expect.objectContaining({ op: "reword", question: "Reworded: who controls the minerals?" }),
      ),
    );
    expect(await screen.findByText(/who controls the minerals/i)).toBeTruthy();
    // Launch approves the CURRENT (edited) tree, then launches it.
    fireEvent.click(await screen.findByRole("button", { name: /Start 3 researches/i }));
    await waitFor(() => expect(approvePlanMock).toHaveBeenCalledWith("q-pn-root"));
    await waitFor(() => expect(launchPlanMock).toHaveBeenCalledWith("q-pn-root", {
      expected_gather_mode: "exa_reasoning",
      allow_contract_stub: false,
      research_tier: "deep",
    }, expect.any(String)));
    await waitFor(() => expect(onLaunched).toHaveBeenCalledWith("sess-edited"));
  });
});

describe("CascadeProposal — honest failure surface (M4)", () => {
  it("renders backend_unreachable when fetch throws", async () => {
    createPlanMock.mockRejectedValue(new TypeError("Failed to fetch"));
    renderProposal();
    expect(await screen.findByText(/research engine isn't running/i)).toBeTruthy();
    expect(screen.queryByText(/model provider isn’t configured/i)).toBeNull();
  });

  it("renders provider_unconfigured from structured 503 envelope", async () => {
    const { ApiError } = await import("../../lib/api");
    createPlanMock.mockRejectedValue(
      new ApiError(
        "fail",
        503,
        JSON.stringify({
          detail: {
            code: "provider_unconfigured",
            message:
              "No model provider is configured. Set a provider key and restart.",
            retryable: false,
          },
        }),
      ),
    );
    renderProposal();
    expect(await screen.findByText(/No model provider is configured/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    expect(screen.getByRole("button", { name: /Ask it as one question instead/i })).toBeTruthy();
  });

  it("renders provider_upstream_error from structured 502 envelope", async () => {
    const { ApiError } = await import("../../lib/api");
    createPlanMock.mockRejectedValue(
      new ApiError(
        "fail",
        502,
        JSON.stringify({
          detail: {
            code: "provider_upstream_error",
            message: "The model provider returned an error. Retry, or check your key's quota.",
            retryable: true,
          },
        }),
      ),
    );
    renderProposal();
    expect(await screen.findByText(/model provider returned an error/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  it("falls back to one-shot when the AI can't split the problem (no sub-questions)", async () => {
    createPlanMock.mockResolvedValue({
      ...CREATE_RESP,
      tree: { ...TREE, root: { ...TREE.root, children: [] } },
    });
    const { onFallBackToAsk } = renderProposal();
    expect(await screen.findByText(/single focused question/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Ask this question" }));
    expect(onFallBackToAsk).toHaveBeenCalledOnce();
  });

  it("offers recovery only for server-attested terminal dispatch leases", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    listLegalPolicyDispatchLeasesMock.mockResolvedValue({
      count: 2,
      leases: [
        {
          lease_id: "lease-active", holder_investigation_id: "child-a",
          acquired_at: "2026-01-01", diagnostic_deadline: "2026-01-01",
          recovery_state: "active", terminal_action: null,
        },
        {
          lease_id: "lease-1", holder_investigation_id: "child-b",
          acquired_at: "2026-01-01", diagnostic_deadline: "2026-01-01",
          recovery_state: "terminal_recoverable",
          terminal_action: "investigation.completed",
        },
      ],
    });
    renderProposal();
    expect(await screen.findByText(/elapsed time cannot release/i)).toBeTruthy();
    const recover = screen.getByRole("button", { name: "Recover terminal run" });
    fireEvent.click(recover);
    fireEvent.click(recover);
    await waitFor(() => expect(recoverLegalPolicyDispatchLeaseMock).toHaveBeenCalledOnce());
    expect(recoverLegalPolicyDispatchLeaseMock.mock.calls[0]?.[0]).toBe("q-pn-root");
    expect(recoverLegalPolicyDispatchLeaseMock.mock.calls[0]?.[1]).toBe("lease-1");
  });
});
