import type { Meta, StoryObj } from "@storybook/react";

import type { PlanTree, ResearchStatus, SessionCost } from "../../api/research";
import CostMeter from "./CostMeter";
import PlanEditor from "./PlanEditor";
import ResearchPanel from "./ResearchPanel";
import { ComposeBar, DeepResearchMissionControlFrame } from "./index";

const meta = {
  title: "Deep Research / Mission Control",
  parameters: { layout: "fullscreen", lostpixel: { waitBeforeScreenshot: 1500 } },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const noop = () => undefined;

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

const COST: SessionCost = {
  per_research: {}, session_total_usd: 8.4, aggregate_spent_usd: 8.4, aggregate_cap_usd: 10,
};

export const Ready: Story = {
  render: () => (
    <div className="h-screen">
      <DeepResearchMissionControlFrame phase="Ready" visualFixture>
        <ComposeBar problem="" setProblem={noop} busy={false} onCreate={noop} />
        <div className="deep-research-mission-control__status">
          <div><strong>One problem becomes an inspectable plan.</strong><p>Nothing launches until the plan is approved.</p></div>
        </div>
      </DeepResearchMissionControlFrame>
    </div>
  ),
};

export const Creating: Story = {
  render: () => (
    <div className="h-screen">
      <DeepResearchMissionControlFrame phase="Charting" visualFixture>
        <ComposeBar problem="How will autonomous research change technology diligence?" setProblem={noop} busy onCreate={noop} />
        <div role="status" className="deep-research-mission-control__status">
          <span className="deep-research-mission-control__spinner" aria-hidden="true" />
          <div><strong>Charting the first research paths…</strong><p>No research has launched yet.</p></div>
        </div>
      </DeepResearchMissionControlFrame>
    </div>
  ),
};

export const DraftPlan: Story = {
  render: () => (
    <div className="h-screen">
      <DeepResearchMissionControlFrame phase="Plan room" visualFixture>
        <ComposeBar problem={TREE.root.question} setProblem={noop} busy={false} onCreate={noop} />
        <PlanEditor tree={TREE} launchable={false} busy={false} onEdit={noop} onApprove={noop} onLaunch={noop} />
      </DeepResearchMissionControlFrame>
    </div>
  ),
};

export const ActiveMonitor: Story = {
  render: () => (
    <div className="h-screen">
      <DeepResearchMissionControlFrame phase="Live session" active visualFixture>
        <CostMeter cost={{ ...COST, session_total_usd: 1.2, aggregate_spent_usd: 1.2 }} />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {RESEARCHES.map((research) => <ResearchPanel key={research.investigation_id} research={research} costUsd={0.042} onSteer={noop} />)}
        </div>
      </DeepResearchMissionControlFrame>
    </div>
  ),
};

export const Failure: Story = {
  render: () => (
    <div className="h-screen">
      <DeepResearchMissionControlFrame phase="Ready" visualFixture>
        <ComposeBar problem="Which evidence would change the investment thesis?" setProblem={noop} busy={false} onCreate={noop} />
        <div role="alert" className="deep-research-mission-control__notice">
          <div><strong>Mission control could not complete that operation.</strong><p>Nothing new was launched or approved. Review the current plan and try again.</p></div>
        </div>
      </DeepResearchMissionControlFrame>
    </div>
  ),
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
