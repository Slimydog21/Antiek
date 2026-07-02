import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";

import InvestigationSidebar, { InvestigationSidebarTree } from "./InvestigationSidebar";
import type { InvestigationSummary } from "../../lib/api";

/**
 * InvestigationSidebar — left dock content in ResearchWorkstation.
 */
export const investigationSidebarStoryInvestigations: InvestigationSummary[] = [
  {
    investigation_id: "inv-memory-architecture",
    question: "How should Antiek reconcile book memory with live research trails?",
    status: "completed",
    started_at: "2026-06-28T15:20:00.000Z",
    completed_at: "2026-06-28T15:45:00.000Z",
    cost_usd_total: 0.0478,
    parent_investigation_id: null,
  },
  {
    investigation_id: "inv-quote-grounding",
    question: "Which retrieved quotes actually support the synthesis claims?",
    status: "in_progress",
    started_at: "2026-06-29T09:12:00.000Z",
    completed_at: null,
    cost_usd_total: 0.0094,
    parent_investigation_id: "inv-memory-architecture",
  },
  {
    investigation_id: "inv-counterargument-map",
    question: "What is the strongest counterargument before drafting?",
    status: "failed",
    started_at: "2026-06-29T10:04:00.000Z",
    completed_at: null,
    cost_usd_total: 0,
    parent_investigation_id: "inv-memory-architecture",
  },
  {
    investigation_id: "inv-reading-routine",
    question: "What should the daily reading workstation surface first?",
    status: "in_progress",
    started_at: "2026-07-01T18:30:00.000Z",
    completed_at: null,
    cost_usd_total: 0.0141,
    parent_investigation_id: null,
    spawned_by_daemon: true,
  },
];

const meta = {
  title: "Loop 1 / InvestigationSidebar",
  component: InvestigationSidebar,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof InvestigationSidebar>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Default render uses deterministic fixture data while preserving the
 * production component's tree-building and row-rendering paths.
 */
export const Default: Story = {
  render: () => (
    <MemoryRouter initialEntries={["/inv/inv-quote-grounding"]}>
      <div className="w-[320px] h-screen bg-ice-2 dark:bg-space-2 border-r-edge border-sun">
        <InvestigationSidebarTree
          investigations={investigationSidebarStoryInvestigations}
          loading={false}
          error={null}
          refetch={() => undefined}
          activeId="inv-quote-grounding"
        />
      </div>
    </MemoryRouter>
  ),
};
