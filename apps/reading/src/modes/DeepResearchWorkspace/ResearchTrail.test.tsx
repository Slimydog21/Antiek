import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import type { PlanTree, ResearchStatus } from "../../api/research";
import ResearchTrail from "./ResearchTrail";

afterEach(cleanup);

const TREE: PlanTree = {
  root: {
    local_id: "root", question: "How should the system change?", rationale: "", focus_boundary: "",
    budget_usd: null, max_depth: null, graph_node_id: "q-root",
    children: [{
      local_id: "branch", question: "Evidence quality", rationale: "Separate the evidence trail.", focus_boundary: "Do not assess pricing.",
      budget_usd: null, max_depth: null, graph_node_id: "q-branch",
      children: [{
        local_id: "leaf", question: "Which sources disagree?", rationale: "Find the contested claim.", focus_boundary: "Primary sources only.",
        budget_usd: null, max_depth: null, graph_node_id: "q-leaf", children: [],
      }],
    }],
  },
  seed_kind: "problem", seed_provenance: {},
  approval: { state: "approved", approved_at: "2026-07-15T00:00:00Z", approved_by: "operator", plan_version: 2 },
  root_investigation_id: "operator",
};

const RESEARCH: ResearchStatus = {
  investigation_id: "session-root-leaf-0",
  sub_question: "Which sources disagree?",
  state: "running",
  question_node_id: "q-leaf",
  plan_node_local_id: "leaf",
  control_available: true,
};

describe("ResearchTrail", () => {
  it("preserves hierarchy and maps controls by graph question identity", () => {
    const onSteer = vi.fn();
    const onFocus = vi.fn();
    render(<ResearchTrail plan={{ root_node_id: "plan-root", tree: TREE }} researches={[RESEARCH]} steeringId={null} onSteer={onSteer} onFocusResearch={onFocus} />);

    expect(screen.getByText("Evidence quality")).toBeTruthy();
    expect(screen.getByText("Separate the evidence trail.")).toBeTruthy();
    expect(screen.getByText("boundary · Primary sources only.")).toBeTruthy();
    expect(screen.getByText("running")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Focus research: Which sources disagree?" }));
    expect(onFocus).toHaveBeenCalledWith(RESEARCH.investigation_id);
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(onSteer).toHaveBeenCalledWith(RESEARCH.investigation_id, "pause");
  });

  it("never guesses a legacy leaf mapping from matching question text", () => {
    const onSteer = vi.fn();
    render(<ResearchTrail
      plan={{ root_node_id: "plan-root", tree: TREE }}
      researches={[{ ...RESEARCH, plan_node_local_id: null }]}
      steeringId={null}
      onSteer={onSteer}
      onFocusResearch={() => {}}
    />);
    expect(screen.getByText("Control unavailable for this older session.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Pause" })).toBeNull();
    expect(onSteer).not.toHaveBeenCalled();
  });

  it("shows recovered nonterminal work as disconnected and removes controls", () => {
    render(<ResearchTrail
      plan={{ root_node_id: "plan-root", tree: TREE }}
      researches={[{ ...RESEARCH, control_available: false }]}
      steeringId={null}
      onSteer={() => {}}
      onFocusResearch={() => {}}
    />);
    expect(screen.getByText("disconnected")).toBeTruthy();
    expect(screen.getByText("Runner disconnected. This durable state cannot be steered.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Pause" })).toBeNull();
  });

  it("fails closed when control authority is omitted", () => {
    const { control_available: _omitted, ...withoutAuthority } = RESEARCH;
    render(<ResearchTrail
      plan={{ root_node_id: "plan-root", tree: TREE }}
      researches={[withoutAuthority]}
      steeringId={null}
      onSteer={() => {}}
      onFocusResearch={() => {}}
    />);
    expect(screen.getByText("disconnected")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Pause" })).toBeNull();
  });
});
