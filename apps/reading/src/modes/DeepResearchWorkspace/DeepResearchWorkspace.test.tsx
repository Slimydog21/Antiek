import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { PlanTree, ResearchStatus } from "../../api/research";
import PlanEditor from "./PlanEditor";
import ResearchPanel from "./ResearchPanel";
import SessionSourceReceipt from "./SessionSourceReceipt";

afterEach(() => cleanup());

const TREE: PlanTree = {
  root: {
    local_id: "pn-root", question: "The problem", rationale: "root", focus_boundary: "",
    budget_usd: null, max_depth: null, graph_node_id: "q-root",
    children: [
      { local_id: "pn-1", question: "Sub one", rationale: "r", focus_boundary: "", budget_usd: null, max_depth: null, graph_node_id: "q-1", children: [] },
      { local_id: "pn-2", question: "Sub two", rationale: "r", focus_boundary: "", budget_usd: null, max_depth: null, graph_node_id: "q-2", children: [] },
    ],
  },
  seed_kind: "problem", seed_provenance: {},
  approval: { state: "draft", approved_at: null, approved_by: null, plan_version: 1 },
  root_investigation_id: "__operator__",
};

describe("PlanEditor — the glass-box gate", () => {
  it("disables Launch until the plan is launchable, and shows the leaf count", () => {
    const onLaunch = vi.fn();
    render(<PlanEditor tree={TREE} launchable={false} onEdit={() => {}} onApprove={() => {}} onLaunch={onLaunch} />);
    const launch = screen.getByRole("button", { name: /Launch 2/ });
    expect((launch as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(launch);
    expect(onLaunch).not.toHaveBeenCalled();
  });

  it("enables Launch once launchable", () => {
    const onLaunch = vi.fn();
    render(<PlanEditor tree={{ ...TREE, approval: { ...TREE.approval, state: "approved" } }}
      launchable onEdit={() => {}} onApprove={() => {}} onLaunch={onLaunch} />);
    const launch = screen.getByRole("button", { name: /Launch 2/ });
    expect((launch as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(launch);
    expect(onLaunch).toHaveBeenCalledOnce();
  });

  it("rewords a sub-question through the edit contract", async () => {
    const onEdit = vi.fn();
    render(<PlanEditor tree={TREE} launchable={false} onEdit={onEdit} onApprove={() => {}} onLaunch={() => {}} />);
    // Hover-revealed 'edit' buttons are in the DOM; click the first one.
    fireEvent.click(screen.getAllByText("edit")[0]);
    const input = await screen.findByLabelText("edit sub-question");
    fireEvent.change(input, { target: { value: "Reworded sub" } });
    fireEvent.submit(input);
    expect(onEdit).toHaveBeenCalledWith(expect.objectContaining({ op: "reword", question: "Reworded sub" }));
  });
});

describe("ResearchPanel — steer controls", () => {
  const running: ResearchStatus = { investigation_id: "inv-0", sub_question: "Q", state: "running" };

  it("routes pause/stop to onSteer for a running research", () => {
    const onSteer = vi.fn();
    render(<ResearchPanel research={running} costUsd={0.01} onSteer={onSteer} />);
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(onSteer).toHaveBeenCalledWith("pause");
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(onSteer).toHaveBeenCalledWith("stop");
  });

  it("hides steer controls for a terminal research", () => {
    render(<ResearchPanel research={{ ...running, state: "done" }} costUsd={0.05} onSteer={() => {}} />);
    expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
    expect(screen.getByText("done")).toBeTruthy();
  });

  it("shows Resume (not Pause) when paused", () => {
    const onSteer = vi.fn();
    render(<ResearchPanel research={{ ...running, state: "paused" }} costUsd={0} onSteer={onSteer} />);
    fireEvent.click(screen.getByRole("button", { name: "Resume" }));
    expect(onSteer).toHaveBeenCalledWith("resume");
  });
});

describe("SessionSourceReceipt", () => {
  it("renders session source metadata without claiming retrieval ran", () => {
    render(
      <SessionSourceReceipt
        policy={["operator_corpus", "web", "arxiv"]}
        execution="metadata_only"
      />,
    );

    expect(screen.getByText("Session sources")).toBeTruthy();
    expect(screen.getByText("Corpus · Web · arXiv")).toBeTruthy();
    expect(screen.getByText(/carried as launch metadata/i)).toBeTruthy();
    expect(screen.getByText(/retrieval receipts arrive separately/i)).toBeTruthy();
  });

  it("renders nothing when no session source policy was recorded", () => {
    const { container } = render(
      <SessionSourceReceipt policy={[]} execution={null} />,
    );

    expect(container.textContent).toBe("");
  });
});

describe("useResearchSession — polling stops at terminal", () => {
  it("polls the durable status endpoint and stops once all terminal", async () => {
    const getSession = vi.fn()
      .mockResolvedValueOnce({
        session_id: "s", live: true,
        researches: [{ investigation_id: "inv-0", sub_question: "Q", state: "running" }],
        cost: { per_research: { "inv-0": 0.01 }, session_total_usd: 0.01, aggregate_spent_usd: 0.01, aggregate_cap_usd: 10 },
        source_policy: ["operator_corpus", "web"],
        source_policy_execution: "metadata_only",
      })
      .mockResolvedValue({
        session_id: "s", live: true,
        researches: [{ investigation_id: "inv-0", sub_question: "Q", state: "done" }],
        cost: { per_research: { "inv-0": 0.03 }, session_total_usd: 0.03, aggregate_spent_usd: 0.03, aggregate_cap_usd: 10 },
        source_policy: ["operator_corpus", "web"],
        source_policy_execution: "metadata_only",
      });
    vi.doMock("../../api/research", async (orig) => ({
      ...(await orig<typeof import("../../api/research")>()),
      getSession,
    }));
    const { useResearchSession } = await import("./useResearchSession");
    const { renderHook } = await import("@testing-library/react");
    const { result } = renderHook(() => useResearchSession("s", { intervalMs: 5 }));
    await waitFor(() => expect(result.current.allTerminal).toBe(true), { timeout: 2000 });
    expect(result.current.researches[0].state).toBe("done");
    expect(result.current.cost?.session_total_usd).toBeCloseTo(0.03);
    expect(result.current.sourcePolicy).toEqual(["operator_corpus", "web"]);
    expect(result.current.sourcePolicyExecution).toBe("metadata_only");
    vi.doUnmock("../../api/research");
  });
});
