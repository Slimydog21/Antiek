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
  approveSpendMock,
  launchPlanMock,
  getBudgetDefaultsMock,
  getPlanMock,
  getSpendPreviewMock,
  getSessionMock,
} = vi.hoisted(() => ({
  createPlanMock: vi.fn(),
  editPlanMock: vi.fn(),
  approvePlanMock: vi.fn(),
  approveSpendMock: vi.fn(),
  launchPlanMock: vi.fn(),
  getBudgetDefaultsMock: vi.fn(),
  getPlanMock: vi.fn(),
  getSpendPreviewMock: vi.fn(),
  getSessionMock: vi.fn(),
}));

vi.mock("../../api/research", async (orig) => {
  const actual = await orig<typeof import("../../api/research")>();
  return {
    ...actual,
    createPlan: createPlanMock,
    editPlan: editPlanMock,
    approvePlan: approvePlanMock,
    approveSpend: approveSpendMock,
    launchPlan: launchPlanMock,
    getBudgetDefaults: getBudgetDefaultsMock,
    getPlan: getPlanMock,
    getSpendPreview: getSpendPreviewMock,
    getSession: getSessionMock,
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
  approveSpendMock.mockReset();
  launchPlanMock.mockReset();
  getBudgetDefaultsMock.mockReset();
  getPlanMock.mockReset();
  getSpendPreviewMock.mockReset();
  getSessionMock.mockReset();
  getBudgetDefaultsMock.mockResolvedValue({ per_research_cost_usd: 0.5, per_research_max_steps: 50 });
  getSpendPreviewMock.mockResolvedValue({
    spend_mode: "hard_ceiling",
    currency: "USD",
    amount_cents: 150,
    eligible: false,
    reasons: ["This automatically generated plan is stop-limit only."],
    authority_digest: null,
    approval_revision: 1,
    assumptions: [],
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
    // 3 sub-questions × $0.50 default per-research limit = a recommended $1.50 stop limit.
    expect(await screen.findByText(/recommended \$1\.50 stop limit for 3 researches/i)).toBeTruthy();
    expect(screen.getByText(/final in-flight steps can exceed it/i)).toBeTruthy();
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
  it("binds hard-mode approval to the exact server-issued authority", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    getSpendPreviewMock.mockResolvedValue({
      spend_mode: "hard_ceiling",
      currency: "USD",
      amount_cents: 150,
      eligible: true,
      reasons: [],
      authority_digest: null,
      approval_revision: 1,
      assumptions: [],
    });
    approvePlanMock.mockResolvedValue({});
    approveSpendMock.mockResolvedValue({
      spend_mode: "hard_ceiling",
      currency: "USD",
      amount_cents: 150,
      eligible: true,
      reasons: [],
      authority_digest: "a".repeat(64),
      approval_revision: 1,
      assumptions: [],
    });
    launchPlanMock.mockResolvedValue({
      session_id: "session-hard",
      researches: [],
      aggregate_cap_usd: null,
    });
    const { onLaunched } = renderProposal();
    const hardMode = await screen.findByRole("button", { name: "Hard ceiling" });
    await waitFor(() => expect((hardMode as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(hardMode);
    const approval = screen.getByRole("checkbox", {
      name: /approve a \$1\.50 hard authorized-spend ceiling/i,
    });
    fireEvent.click(approval);
    await waitFor(() => expect((approval as HTMLInputElement).checked).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: /Start 3 researches/i }));
    await waitFor(() =>
      expect(launchPlanMock).toHaveBeenCalledWith("q-pn-root", {
        spend_mode: "hard_ceiling",
        hard_ceiling_usd: "1.50",
        authority_digest: "a".repeat(64),
      }),
    );
    expect(approvePlanMock).toHaveBeenCalledOnce();
    expect(approveSpendMock).toHaveBeenCalledWith("q-pn-root", "1.50");
    expect(onLaunched).toHaveBeenCalledWith("session-hard");
  });

  it("revokes hard authority synchronously when the ceiling changes", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    getSpendPreviewMock.mockResolvedValue({
      spend_mode: "hard_ceiling", currency: "USD", amount_cents: 150,
      eligible: true, reasons: [], authority_digest: null, approval_revision: 1, assumptions: [],
    });
    approvePlanMock.mockResolvedValue({});
    approveSpendMock.mockResolvedValue({
      spend_mode: "hard_ceiling", currency: "USD", amount_cents: 150,
      eligible: true, reasons: [], authority_digest: "b".repeat(64), approval_revision: 1, assumptions: [],
    });
    renderProposal();
    const hardMode = await screen.findByRole("button", { name: "Hard ceiling" });
    await waitFor(() => expect((hardMode as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(hardMode);
    const approval = screen.getByRole("checkbox", { name: /hard authorized-spend ceiling/i });
    fireEvent.click(approval);
    await waitFor(() => expect((approval as HTMLInputElement).checked).toBe(true));
    fireEvent.change(screen.getByRole("spinbutton", { name: "Authorized spend ceiling" }), {
      target: { value: "2.00" },
    });
    expect((approval as HTMLInputElement).checked).toBe(false);
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
    fireEvent.click(screen.getByRole("checkbox", { name: /approve a \$1\.50 aggregate stop limit/i }));
    // Remove the third sub-question.
    fireEvent.click(screen.getAllByRole("button", { name: "remove" })[2]);
    await waitFor(() =>
      expect(editPlanMock).toHaveBeenCalledWith(
        "q-pn-root",
        expect.objectContaining({ op: "remove", target_local_id: "pn-3" }),
      ),
    );
    await waitFor(() => expect(screen.queryByText(/chokepoints replace oil/i)).toBeNull());
    const revisedApproval = screen.getByRole("checkbox", { name: /approve a \$1\.00 aggregate stop limit/i });
    expect((revisedApproval as HTMLInputElement).checked).toBe(false);
    expect((screen.getByRole("button", { name: /Start 2 researches/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("revokes approval while an edit is in flight so the stale tree cannot launch", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    let resolveEdit!: (value: PlanResponse) => void;
    editPlanMock.mockReturnValue(
      new Promise<PlanResponse>((resolve) => {
        resolveEdit = resolve;
      }),
    );
    renderProposal();
    const launch = await screen.findByRole("button", { name: /Start 3 researches/i });
    const approval = screen.getByRole("checkbox", {
      name: /approve a \$1\.50 aggregate stop limit/i,
    });
    fireEvent.click(approval);
    expect((launch as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(screen.getAllByRole("button", { name: "remove" })[2]);
    expect((approval as HTMLInputElement).checked).toBe(false);
    expect((approval as HTMLInputElement).disabled).toBe(true);
    expect((launch as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(launch);
    expect(approvePlanMock).not.toHaveBeenCalled();
    expect(launchPlanMock).not.toHaveBeenCalled();

    resolveEdit({
      root_node_id: "q-pn-root",
      tree: { ...TREE, root: { ...TREE.root, children: TREE.root.children.slice(0, 2) } },
      launchable: false,
    });
    await screen.findByRole("button", { name: /Start 2 researches/i });
    expect(
      (screen.getByRole("checkbox", {
        name: /approve a \$1\.00 aggregate stop limit/i,
      }) as HTMLInputElement).checked,
    ).toBe(false);
  });

  it("fails closed when an edit response is lost instead of launching a stale visible tree", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    editPlanMock.mockRejectedValue(new TypeError("Failed to fetch"));
    renderProposal();
    await screen.findByText(/chokepoints replace oil/i);
    fireEvent.click(screen.getAllByRole("button", { name: "remove" })[2]);

    expect(await screen.findByText(/Couldn’t update the research plan/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Start 3 researches/i })).toBeNull();
    expect(approvePlanMock).not.toHaveBeenCalled();
    expect(launchPlanMock).not.toHaveBeenCalled();
  });

  it("reloads authoritative plan state after an ambiguous edit failure", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    editPlanMock.mockRejectedValue(new TypeError("Failed to fetch"));
    getPlanMock.mockResolvedValue({
      root_node_id: "q-pn-root",
      tree: { ...TREE, root: { ...TREE.root, children: TREE.root.children.slice(0, 2) } },
      launchable: false,
    });
    renderProposal();
    await screen.findByText(/chokepoints replace oil/i);
    fireEvent.click(screen.getAllByRole("button", { name: "remove" })[2]);
    fireEvent.click(await screen.findByRole("button", { name: "Reload plan" }));

    expect(await screen.findByRole("button", { name: /Start 2 researches/i })).toBeTruthy();
    expect(getPlanMock).toHaveBeenCalledWith("q-pn-root");
    expect(screen.queryByText(/chokepoints replace oil/i)).toBeNull();
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
    expect((launch as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(await screen.findByRole("checkbox", { name: /approve a \$1\.50 aggregate stop limit/i }));
    fireEvent.click(launch);
    await waitFor(() => expect(approvePlanMock).toHaveBeenCalledWith("q-pn-root"));
    await waitFor(() =>
      expect(launchPlanMock).toHaveBeenCalledWith("q-pn-root", {
        aggregate_budget_usd: 1.5,
      }),
    );
    await waitFor(() => expect(onLaunched).toHaveBeenCalledWith("session-q-pn-root"));
  });

  it("freezes plan and budget controls while approval and launch are in flight", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    let resolveApproval!: (value: unknown) => void;
    approvePlanMock.mockReturnValue(
      new Promise((resolve) => {
        resolveApproval = resolve;
      }),
    );
    launchPlanMock.mockResolvedValue({
      session_id: "session-q-pn-root",
      researches: [],
      aggregate_cap_usd: 1.5,
    });
    renderProposal();
    const launch = await screen.findByRole("button", { name: /Start 3 researches/i });
    fireEvent.click(
      screen.getByRole("checkbox", { name: /approve a \$1\.50 aggregate stop limit/i }),
    );
    fireEvent.click(launch);

    expect(await screen.findByRole("button", { name: "Starting…" })).toBeTruthy();
    expect((screen.getAllByRole("button", { name: "edit" })[0] as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getAllByRole("button", { name: "remove" })[0] as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("spinbutton", { name: "Aggregate stop limit" }) as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: /Ask one question instead/i }) as HTMLButtonElement).disabled).toBe(true);
    expect(editPlanMock).not.toHaveBeenCalled();

    resolveApproval({});
    await waitFor(() => expect(launchPlanMock).toHaveBeenCalledOnce());
  });

  it("recovers an existing session after a launch response is lost", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    approvePlanMock.mockResolvedValue({});
    launchPlanMock.mockRejectedValue(new TypeError("Failed to fetch"));
    getSessionMock.mockResolvedValue({
      session_id: "session-q-pn-root",
      live: true,
      researches: [],
    });
    const { onLaunched } = renderProposal();
    const launch = await screen.findByRole("button", { name: /Start 3 researches/i });
    fireEvent.click(
      screen.getByRole("checkbox", { name: /approve a \$1\.50 aggregate stop limit/i }),
    );
    fireEvent.click(launch);
    fireEvent.click(await screen.findByRole("button", { name: "Check launch status" }));

    await waitFor(() => expect(getSessionMock).toHaveBeenCalledWith("session-q-pn-root"));
    expect(onLaunched).toHaveBeenCalledWith("session-q-pn-root");
    expect(createPlanMock).toHaveBeenCalledOnce();
  });

  it("replays the exact hard authority after a launch response is lost", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    getSpendPreviewMock.mockResolvedValue({
      spend_mode: "hard_ceiling", currency: "USD", amount_cents: 150,
      eligible: true, reasons: [], authority_digest: null, recovery_session_id: null,
      approval_revision: 1, assumptions: [],
    });
    approvePlanMock.mockResolvedValue({});
    approveSpendMock.mockResolvedValue({
      spend_mode: "hard_ceiling", currency: "USD", amount_cents: 150,
      eligible: true, reasons: [], authority_digest: "c".repeat(64),
      recovery_session_id: "session-q-pn-root-hard-server-issued",
      approval_revision: 1, assumptions: [],
    });
    launchPlanMock.mockRejectedValueOnce(new TypeError("Failed to fetch")).mockResolvedValue({
      session_id: "session-q-pn-root-hard-server-issued",
      researches: [],
      aggregate_cap_usd: null,
    });
    const { onLaunched } = renderProposal();
    const hardMode = await screen.findByRole("button", { name: "Hard ceiling" });
    await waitFor(() => expect((hardMode as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(hardMode);
    const approval = screen.getByRole("checkbox", { name: /hard authorized-spend ceiling/i });
    fireEvent.click(approval);
    await waitFor(() => expect((approval as HTMLInputElement).checked).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: /Start 3 researches/i }));
    fireEvent.click(await screen.findByRole("button", { name: "Check launch status" }));

    await waitFor(() => expect(launchPlanMock).toHaveBeenCalledTimes(2));
    expect(launchPlanMock).toHaveBeenLastCalledWith("q-pn-root", {
      spend_mode: "hard_ceiling",
      hard_ceiling_usd: "1.50",
      authority_digest: "c".repeat(64),
    });
    expect(getSessionMock).not.toHaveBeenCalled();
    expect(onLaunched).toHaveBeenCalledWith("session-q-pn-root-hard-server-issued");
  });

  it("reloads the plan when approval fails before launch", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    approvePlanMock.mockRejectedValue(new TypeError("Failed to fetch"));
    getPlanMock.mockResolvedValue({
      root_node_id: "q-pn-root",
      tree: TREE,
      launchable: true,
    });
    renderProposal();
    const launch = await screen.findByRole("button", { name: /Start 3 researches/i });
    fireEvent.click(
      screen.getByRole("checkbox", { name: /approve a \$1\.50 aggregate stop limit/i }),
    );
    fireEvent.click(launch);
    fireEvent.click(await screen.findByRole("button", { name: "Reload plan" }));

    expect(await screen.findByRole("button", { name: /Start 3 researches/i })).toBeTruthy();
    expect(getPlanMock).toHaveBeenCalledWith("q-pn-root");
    expect(launchPlanMock).not.toHaveBeenCalled();
  });

  it("returns to the authoritative plan when launch status confirms no session", async () => {
    const { ApiError } = await import("../../lib/api");
    createPlanMock.mockResolvedValue(CREATE_RESP);
    approvePlanMock.mockResolvedValue({});
    launchPlanMock.mockRejectedValue(new TypeError("Failed to fetch"));
    getSessionMock.mockRejectedValue(new ApiError("missing", 404, "{}"));
    getPlanMock.mockResolvedValue({
      root_node_id: "q-pn-root",
      tree: TREE,
      launchable: true,
    });
    renderProposal();
    const launch = await screen.findByRole("button", { name: /Start 3 researches/i });
    fireEvent.click(
      screen.getByRole("checkbox", { name: /approve a \$1\.50 aggregate stop limit/i }),
    );
    fireEvent.click(launch);
    fireEvent.click(await screen.findByRole("button", { name: "Check launch status" }));

    const recoveredLaunch = await screen.findByRole("button", { name: /Start 3 researches/i });
    expect((recoveredLaunch as HTMLButtonElement).disabled).toBe(true);
    expect(getPlanMock).toHaveBeenCalledWith("q-pn-root");
  });

  it("requires a valid explicit stop limit and invalidates approval when it changes", async () => {
    createPlanMock.mockResolvedValue(CREATE_RESP);
    renderProposal();
    const launch = await screen.findByRole("button", { name: /Start 3 researches/i });
    const ceiling = screen.getByRole("spinbutton", { name: "Aggregate stop limit" });
    const approval = screen.getByRole("checkbox", { name: /approve a \$1\.50 aggregate stop limit/i });
    fireEvent.click(approval);
    expect((launch as HTMLButtonElement).disabled).toBe(false);

    fireEvent.change(ceiling, { target: { value: "0" } });
    expect(screen.getByRole("alert").textContent).toMatch(/positive amount/i);
    expect((approval as HTMLInputElement).checked).toBe(false);
    expect((approval as HTMLInputElement).disabled).toBe(true);
    expect((launch as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(ceiling, { target: { value: "2.25" } });
    const updatedApproval = screen.getByRole("checkbox", { name: /approve a \$2\.25 aggregate stop limit/i });
    expect((updatedApproval as HTMLInputElement).disabled).toBe(false);
    fireEvent.click(updatedApproval);
    expect((launch as HTMLButtonElement).disabled).toBe(false);
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
    fireEvent.click(screen.getByRole("checkbox", { name: /approve a \$1\.50 aggregate stop limit/i }));
    fireEvent.click(await screen.findByRole("button", { name: /Start 3 researches/i }));
    await waitFor(() => expect(approvePlanMock).toHaveBeenCalledWith("q-pn-root"));
    await waitFor(() =>
      expect(launchPlanMock).toHaveBeenCalledWith("q-pn-root", {
        aggregate_budget_usd: 1.5,
      }),
    );
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
});
