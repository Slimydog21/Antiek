import type { Meta, StoryObj } from "@storybook/react";

import type { PlanTree, ResearchStatus, SessionCost } from "../../api/research";
import CostMeter from "./CostMeter";
import PlanEditor from "./PlanEditor";
import ResearchPanel from "./ResearchPanel";
import ResearchTrail from "./ResearchTrail";

const meta = {
  title: "DeepResearch / Workspace",
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const TREE: PlanTree = {
  root: {
    local_id: "pn-root", question: "Is the web-gaming wedge investable at $25-50M?",
    rationale: "root problem", focus_boundary: "", budget_usd: null, max_depth: null,
    graph_node_id: "q-root",
    children: [
      { local_id: "pn-1", question: "What is Rosebud's retention curve?", rationale: "binary diligence blocker", focus_boundary: "metrics", budget_usd: null, max_depth: null, graph_node_id: "q-1", children: [] },
      { local_id: "pn-2", question: "How does behavioral moderation scale?", rationale: "binary diligence blocker", focus_boundary: "ops", budget_usd: null, max_depth: null, graph_node_id: "q-2", children: [] },
      { local_id: "pn-3", question: "Roblox's platform-risk exposure?", rationale: "competitive", focus_boundary: "market", budget_usd: null, max_depth: null, graph_node_id: "q-3", children: [] },
    ],
  },
  seed_kind: "problem", seed_provenance: {},
  approval: { state: "draft", approved_at: null, approved_by: null, plan_version: 1 },
  root_investigation_id: "__operator__",
};

export const Plan_Draft: Story = {
  render: () => (
    <PlanEditor tree={TREE} launchable={false} onEdit={() => {}} onApprove={() => {}} onLaunch={() => {}} />
  ),
};

export const Plan_Approved: Story = {
  render: () => (
    <PlanEditor
      tree={{ ...TREE, approval: { ...TREE.approval, state: "approved" } }}
      launchable
      onEdit={() => {}} onApprove={() => {}} onLaunch={() => {}}
    />
  ),
};

const RESEARCHES: ResearchStatus[] = [
  { investigation_id: "session-x-leaf-0", sub_question: "What is Rosebud's retention curve?", state: "running" },
  { investigation_id: "session-x-leaf-1", sub_question: "How does behavioral moderation scale?", state: "paused" },
  { investigation_id: "session-x-leaf-2", sub_question: "Roblox's platform-risk exposure?", state: "done" },
  { investigation_id: "session-x-leaf-3", sub_question: "A research that hit its budget cap", state: "budget_halted" },
];

export const Research_Panels: Story = {
  render: () => (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {RESEARCHES.map((r) => (
        <ResearchPanel key={r.investigation_id} research={r} costUsd={0.042} onSteer={() => {}} />
      ))}
    </div>
  ),
};

export const Live_Research_Trail: Story = {
  render: () => (
    <div className="max-w-md">
      <ResearchTrail
        plan={{
          root_node_id: "plan-root",
          tree: { ...TREE, approval: { ...TREE.approval, state: "approved" } },
        }}
        researches={TREE.root.children.map((node, index) => ({
          investigation_id: `session-x-leaf-${index}`,
          sub_question: node.question,
          state: (["running", "paused", "done"] as const)[index],
          question_node_id: node.graph_node_id,
          plan_node_local_id: node.local_id,
          control_available: true,
        }))}
        steeringId={null}
        onSteer={() => {}}
        onFocusResearch={() => {}}
      />
    </div>
  ),
};

const COST: SessionCost = {
  per_research: {}, session_total_usd: 8.4, aggregate_spent_usd: 8.4, aggregate_cap_usd: 10,
};

export const Cost_Meter: Story = {
  render: () => (
    <div className="flex w-72 flex-col gap-4">
      <CostMeter cost={{ ...COST, session_total_usd: 1.2, aggregate_spent_usd: 1.2 }} />
      <CostMeter cost={COST} />
      <CostMeter cost={{ ...COST, session_total_usd: 10, aggregate_spent_usd: 10 }} />
    </div>
  ),
};
