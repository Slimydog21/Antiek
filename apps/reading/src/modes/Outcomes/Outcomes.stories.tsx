import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";

import Outcomes from "./index";
import type { OutcomeRow } from "./index";

const empty = async (): Promise<OutcomeRow[]> => [];
const loading = () => new Promise<OutcomeRow[]>(() => {});
const failure = async (): Promise<OutcomeRow[]> => {
  throw new Error("Outcome archive unavailable");
};
const history: OutcomeRow[] = [
  {
    outcome_id: "outcome_01",
    observer: "__operator__",
    observed_at: "2026-07-16T10:30:00Z",
    thesis_outcomes: [
      {
        kind: "validated",
        note: "The primary claim survived the cited counterevidence.",
      },
    ],
    falsification_outcomes: [],
    execution_risk_outcomes: [],
    notes: "The conclusion is bounded to the reviewed source set.",
  },
  {
    outcome_id: "outcome_02",
    observer: "__operator__",
    observed_at: "2026-07-15T18:10:00Z",
    thesis_outcomes: [],
    falsification_outcomes: [],
    execution_risk_outcomes: [
      {
        kind: "indeterminate",
        note: "The deployment evidence is still incomplete.",
      },
    ],
    notes: null,
  },
];

const meta = {
  title: "Outcomes / Verdict Chamber",
  component: Outcomes,
  render: (args) => (
    <MemoryRouter>
      <Outcomes {...args} executionEnabled={false} />
    </MemoryRouter>
  ),
  argTypes: { executionEnabled: { control: false, table: { disable: true } } },
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof Outcomes>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Empty: Story = {
  args: { synthesisIdOverride: "syn_fixture", loadOutcomes: empty },
};
export const Loading: Story = {
  args: { synthesisIdOverride: "syn_fixture", loadOutcomes: loading },
};
export const Populated: Story = {
  args: {
    synthesisIdOverride: "syn_fixture",
    loadOutcomes: async () => history,
  },
};
export const SafeFailure: Story = {
  args: { synthesisIdOverride: "syn_fixture", loadOutcomes: failure },
};
export const Night: Story = {
  args: {
    synthesisIdOverride: "syn_fixture",
    loadOutcomes: async () => history,
  },
  parameters: { backgrounds: { default: "dark" } },
};
export const Narrow: Story = {
  args: {
    synthesisIdOverride: "syn_fixture",
    loadOutcomes: async () => history,
  },
  parameters: { viewport: { defaultViewport: "mobile1" } },
};
