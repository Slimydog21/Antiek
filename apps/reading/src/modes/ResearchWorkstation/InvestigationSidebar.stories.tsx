/** Literal fixtures keep visual evidence independent of network and wall clock. */
import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter, useParams } from "react-router-dom";

import { ResearchIndexView } from "./InvestigationSidebar";
import type { ResearchIndexViewProps, TreeNode } from "./InvestigationSidebar";
import type { InvestigationSummary } from "../../lib/api";

const FIXED_NOW_MS = Date.parse("2026-07-15T12:00:00Z");

function inv(
  over: Partial<InvestigationSummary> & { investigation_id: string },
): InvestigationSummary {
  return {
    question: "A research question",
    status: "completed",
    started_at: "2026-07-10T09:00:00Z",
    completed_at: null,
    cost_usd_total: 0,
    parent_investigation_id: null,
    ...over,
  };
}

function node(
  summary: InvestigationSummary,
  children: TreeNode[] = [],
): TreeNode {
  return { investigationId: summary.investigation_id, summary, children };
}

const root = inv({
  investigation_id: "inv-root-001",
  question: "What are the economic effects of deep-sea mining on Pacific Island nations?",
  status: "completed",
  started_at: "2026-07-10T09:00:00Z",
  cost_usd_total: 0.1234,
});

const child1 = inv({
  investigation_id: "inv-child-001",
  question: "How does deep-sea mining affect tuna fisheries in the EEZ?",
  status: "in_progress",
  started_at: "2026-07-10T09:50:00Z",
  cost_usd_total: 0.0456,
  parent_investigation_id: "inv-root-001",
  spawned_by_daemon: true,
});

const child2 = inv({
  investigation_id: "inv-child-002",
  question: "What compensation frameworks exist for seabed resource extraction?",
  status: "failed",
  started_at: "2026-07-10T09:52:00Z",
  cost_usd_total: 0.0789,
  parent_investigation_id: "inv-root-001",
});

const grandchild = inv({
  investigation_id: "inv-grandchild-001",
  question: "Has the ISA issued any provisional licenses in the Clarion-Clipperton Zone since 2024?",
  status: "stopped",
  started_at: "2026-07-10T10:00:00Z",
  cost_usd_total: 0.0111,
  parent_investigation_id: "inv-child-002",
});

const standalone = inv({
  investigation_id: "inv-standalone-001",
  question: "What is the current state of mRNA vaccine patents globally?",
  status: "completed",
  started_at: "2026-07-09T14:00:00Z",
  cost_usd_total: 0.0320,
});

const notFound = inv({
  investigation_id: "inv-notfound-001",
  question: "A research that went missing",
  status: "not_found",
  started_at: "2026-07-08T10:00:00Z",
  cost_usd_total: 0.0001,
});

const FULL_TREE: TreeNode[] = [
  node(root, [
    node(child1),
    node(child2, [
      node(grandchild),
    ]),
  ]),
  node(standalone),
  node(notFound),
];

const meta = {
  title: "ResearchWorkstation / ResearchIndexView",
  component: ResearchIndexView,
  parameters: {
    layout: "fullscreen",
  },
  decorators: [
    (Story) => (
      <div className="w-[320px] h-screen bg-ice-2 dark:bg-space-2 border-r border-rule">
        <Story />
      </div>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof ResearchIndexView>;

export default meta;
type Story = StoryObj<typeof meta>;

export const FullLineage: Story = {
  args: {
    tree: FULL_TREE,
    activeId: "inv-child-001",
    loading: false,
    error: null,
    onRefresh: () => {},
    nowMs: FIXED_NOW_MS,
  },
};

function RoutedFixture() {
  const { investigationId } = useParams<{ investigationId?: string }>();
  return (
    <ResearchIndexView
      {...FullLineage.args!}
      activeId={investigationId ?? null}
    />
  );
}

export const RoutedActiveChild: Story = {
  parameters: { router: false },
  render: () => (
    <MemoryRouter initialEntries={["/inv/inv-child-001"]}>
      <RoutedFixture />
    </MemoryRouter>
  ),
};

export const Narrow: Story = {
  args: { ...FullLineage.args },
  parameters: {
    viewport: { defaultViewport: "mobile1" },
  },
  decorators: [
    (Story) => (
      <div className="w-[240px] h-screen bg-ice-2 dark:bg-space-2 border-r border-rule overflow-x-hidden">
        <Story />
      </div>
    ),
  ],
};

export const Loading: Story = {
  args: {
    tree: [],
    activeId: null,
    loading: true,
    error: null,
    onRefresh: () => {},
    nowMs: FIXED_NOW_MS,
  },
};

export const Empty: Story = {
  args: {
    tree: [],
    activeId: null,
    loading: false,
    error: null,
    onRefresh: () => {},
    nowMs: FIXED_NOW_MS,
  },
};

export const TerminalError: Story = {
  args: {
    tree: [],
    activeId: null,
    loading: false,
    error: "Connection refused",
    onRefresh: () => {},
    nowMs: FIXED_NOW_MS,
  },
};

export const StaleData: Story = {
  args: {
    tree: FULL_TREE,
    activeId: null,
    loading: false,
    error: "Network timeout",
    onRefresh: () => {},
    nowMs: FIXED_NOW_MS,
  },
};
