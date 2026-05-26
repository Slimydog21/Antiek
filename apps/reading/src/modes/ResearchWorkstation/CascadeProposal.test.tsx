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
  getBudgetDefaultsMock,
} = vi.hoisted(() => ({
  createPlanMock: vi.fn(),
  editPlanMock: vi.fn(),
  approvePlanMock: vi.fn(),
  launchPlanMock: vi.fn(),
  getBudgetDefaultsMock: vi.fn(),
}));

vi.mock("../../api/research", async (orig) => {
  const actual = await orig<typeof import("../../api/research")>();
  return {
    ...actual,
    createPlan: createPlanMock,
    editPlan: editPlanMock,
    approvePlan: approvePlanMock,
    launchPlan: launchPlanMock,
    getBudgetDefaults: getBudgetDefaultsMock,
  };
});

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
  createPlanMock.mockReset();
  editPlanMock.mockReset();
  approvePlanMock.mockReset();
  launchPlanMock.mockReset();
  getBudgetDefaultsMock.mockReset();
  getBudgetDefaultsMock.mockResolvedValue({ per_research_cost_usd: 0.5, per_research_max_steps: 50 });
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
    await waitFor(() => expect(launchPlanMock).toHaveBeenCalledWith("q-pn-root"));
    await waitFor(() => expect(onLaunched).toHaveBeenCalledWith("session-q-pn-root"));
  });
});

describe("CascadeProposal — honest no-key state (M4)", () => {
  it("renders the shared AIActionFailure when the propose call fails (no provider keys)", async () => {
    createPlanMock.mockRejectedValue(new Error("HTTP 500"));
    renderProposal();
    // Same honest sentence the one-shot path uses on a no-result failure.
    expect(await screen.findByText(/Couldn’t break this into sub-questions/i)).toBeTruthy();
    expect(screen.getByText(/model provider isn’t configured/i)).toBeTruthy();
    // No fake tree.
    expect(screen.queryByText(/critical-mineral supply/i)).toBeNull();
    // A retry and a one-shot escape hatch are both offered.
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Ask it as one question instead/i })).toBeTruthy();
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
});
