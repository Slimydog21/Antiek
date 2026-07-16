import type { Meta, StoryObj } from "@storybook/react";
import { StatsView } from "./index";

const complete = {
  counts: {
    investigations: 1284,
    documents: 98523,
    chunks: 1200456,
    nodes: 741002,
    edges: 2400110,
    notebooks: 42,
    notebook_blocks: 1844,
    interview_projects: 8,
    interviews: 96,
    ip_holders: 17,
    payout_transfers: 326,
    outcomes: 64,
    skill_rules: 21,
    deletion_requests: 3,
  },
  warnings: [],
};
const meta = {
  title: "Modes/Substrate Atlas",
  component: StatsView,
  parameters: { layout: "fullscreen" },
  args: { data: complete, onRefresh: () => undefined },
} satisfies Meta<typeof StatsView>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Measured: Story = {};
export const KnownZero: Story = {
  args: { data: { counts: { investigations: 0 }, warnings: [] } },
};
export const Loading: Story = { args: { data: null, loading: true } };
export const MissingCounts: Story = {
  args: { data: { counts: { investigations: 9 }, warnings: [] } },
};
export const IntegrityWarning: Story = {
  args: {
    data: {
      counts: { investigations: 9 },
      warnings: ["private detail", "another detail"],
    },
  },
};
export const SafeError: Story = { args: { data: null, error: true } };
export const LongCount: Story = {
  args: {
    data: {
      counts: { investigations: Number.MAX_SAFE_INTEGER },
      warnings: [],
    },
  },
};
export const Narrow: Story = {
  args: { data: complete },
  parameters: { viewport: { defaultViewport: "mobile1" } },
};
