import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { PlanTree, ResearchStatus } from "../../api/research";
import CostMeter from "./CostMeter";
import PlanEditor from "./PlanEditor";
import ResearchPanel from "./ResearchPanel";
import { launchedChildIdsFromSession } from "./sessionLineage";

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

  it("sets per-node budget and depth through the edit contract", async () => {
    const onEdit = vi.fn();
    render(<PlanEditor tree={TREE} launchable={false} onEdit={onEdit} onApprove={() => {}} onLaunch={() => {}} />);
    fireEvent.click(screen.getAllByText("budget")[0]);

    const budget = screen.getByLabelText("budget USD");
    const maxDepth = screen.getByLabelText("max depth");
    fireEvent.change(budget, { target: { value: "0.75" } });
    fireEvent.change(maxDepth, { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Save limits" }));

    expect(onEdit).toHaveBeenCalledWith({
      op: "set_budget",
      target_local_id: "pn-root",
      budget_usd: 0.75,
      max_depth: 4,
    });
  });

  it("does not submit empty or invalid budget edits", async () => {
    const onEdit = vi.fn();
    render(<PlanEditor tree={TREE} launchable={false} onEdit={onEdit} onApprove={() => {}} onLaunch={() => {}} />);
    fireEvent.click(screen.getAllByText("budget")[0]);

    const save = screen.getByRole("button", { name: "Save limits" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("budget USD"), { target: { value: "0.75" } });
    fireEvent.change(screen.getByLabelText("max depth"), { target: { value: "4.5" } });
    expect(save.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("max depth"), { target: { value: "9007199254740992" } });
    expect(save.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("max depth"), { target: { value: "4" } });
    expect(save.disabled).toBe(false);
  });

  it("splits a broad node into focused sub-questions through the edit contract", async () => {
    const onEdit = vi.fn();
    render(<PlanEditor tree={TREE} launchable={false} onEdit={onEdit} onApprove={() => {}} onLaunch={() => {}} />);
    fireEvent.click(screen.getAllByText("split")[0]);

    const textarea = await screen.findByLabelText("split sub-questions");
    fireEvent.change(textarea, { target: { value: "First narrower question\n\nSecond narrower question" } });
    fireEvent.click(screen.getByRole("button", { name: "Split" }));

    expect(onEdit).toHaveBeenCalledWith({
      op: "split",
      target_local_id: "pn-root",
      into: ["First narrower question", "Second narrower question"],
    });
  });

  it("requires at least two split targets before sending a split edit", async () => {
    const onEdit = vi.fn();
    render(<PlanEditor tree={TREE} launchable={false} onEdit={onEdit} onApprove={() => {}} onLaunch={() => {}} />);
    fireEvent.click(screen.getAllByText("split")[1]);

    const split = screen.getByRole("button", { name: "Split" }) as HTMLButtonElement;
    expect(split.disabled).toBe(true);

    const textarea = await screen.findByLabelText("split sub-questions");
    fireEvent.change(textarea, { target: { value: "Only one narrower question" } });
    expect(split.disabled).toBe(true);
    fireEvent.click(split);
    expect(onEdit).not.toHaveBeenCalled();

    fireEvent.change(textarea, { target: { value: "First leaf split\nSecond leaf split" } });
    expect(split.disabled).toBe(false);
    fireEvent.click(split);
    expect(onEdit).toHaveBeenCalledWith({
      op: "split",
      target_local_id: "pn-1",
      into: ["First leaf split", "Second leaf split"],
    });
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

  it("hides steer controls while a stop request is sealing", () => {
    render(<ResearchPanel research={{ ...running, state: "stopping" }} costUsd={0.02} onSteer={() => {}} />);
    expect(screen.getByText("stopping")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Pause" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Redirect" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Deepen" })).toBeNull();
  });

  it("shows Resume (not Pause) when paused", () => {
    const onSteer = vi.fn();
    render(<ResearchPanel research={{ ...running, state: "paused" }} costUsd={0} onSteer={onSteer} />);
    fireEvent.click(screen.getByRole("button", { name: "Resume" }));
    expect(onSteer).toHaveBeenCalledWith("resume");
  });

  it("surfaces a refused steer command on the owning research card", async () => {
    render(
      <ResearchPanel
        research={running}
        costUsd={0.01}
        onSteer={vi.fn().mockRejectedValue(new Error("budget already halted"))}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Stop" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Steer failed: budget already halted");
  });

  it("sanitizes malformed per-research cost", () => {
    render(<ResearchPanel research={running} costUsd={Number.NaN} onSteer={() => {}} />);

    expect(screen.getByText("$0.0000")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-/);
  });
});

describe("Monitor — launched child ids", () => {
  it("derives launched child labels only from known session research ids", () => {
    const launched = launchedChildIdsFromSession([
      { investigation_id: "inv-child-a" },
      { investigation_id: "inv-child-b" },
    ]);

    expect(launched.has("inv-child-a")).toBe(true);
    expect(launched.has("inv-child-b")).toBe(true);
    expect(launched.has("reserved-but-not-launched")).toBe(false);
  });
});

describe("CostMeter — session spend against aggregate cap", () => {
  it("renders an awaiting state before the session reports cost", () => {
    render(<CostMeter cost={null} />);
    expect(screen.getByText("cost · awaiting session")).toBeTruthy();
  });

  it("displays session total while using aggregate spend for budget state", () => {
    render(
      <CostMeter
        cost={{
          per_research: { "inv-1": 0.1 },
          session_total_usd: 0.1,
          aggregate_spent_usd: 8.5,
          aggregate_cap_usd: 10,
        }}
      />,
    );

    expect(screen.getByText("$0.1000")).toBeTruthy();
    expect(screen.getByText("Approaching the aggregate budget.")).toBeTruthy();
  });

  it("flags cap reached from aggregate spend, not the displayed session total", () => {
    render(
      <CostMeter
        cost={{
          per_research: { "inv-1": 0.5 },
          session_total_usd: 0.5,
          aggregate_spent_usd: 10,
          aggregate_cap_usd: 10,
        }}
      />,
    );

    expect(screen.getByText("$0.5000")).toBeTruthy();
    expect(screen.getByText("Aggregate budget reached — new launches are blocked until the cap is lifted.")).toBeTruthy();
  });

  it("sanitizes malformed session cost values", () => {
    render(
      <CostMeter
        cost={{
          per_research: {},
          session_total_usd: Number.NaN,
          aggregate_spent_usd: Number.POSITIVE_INFINITY,
          aggregate_cap_usd: -1,
        }}
      />,
    );

    expect(screen.getByText("$0.0000")).toBeTruthy();
    expect(screen.getByText("/ $0.00")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-/);
  });
});

describe("useResearchSession — polling stops at terminal", () => {
  it("polls the durable status endpoint and stops once all terminal", async () => {
    const getSession = vi.fn()
      .mockResolvedValueOnce({
        session_id: "s", live: true,
        researches: [{ investigation_id: "inv-0", sub_question: "Q", state: "running" }],
        cost: { per_research: { "inv-0": 0.01 }, session_total_usd: 0.01, aggregate_spent_usd: 0.01, aggregate_cap_usd: 10 },
      })
      .mockResolvedValue({
        session_id: "s", live: true,
        researches: [{ investigation_id: "inv-0", sub_question: "Q", state: "done" }],
        cost: { per_research: { "inv-0": 0.03 }, session_total_usd: 0.03, aggregate_spent_usd: 0.03, aggregate_cap_usd: 10 },
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
    vi.doUnmock("../../api/research");
  });
});
