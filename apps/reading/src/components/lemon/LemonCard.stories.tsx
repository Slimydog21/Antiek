import type { Meta, StoryObj } from "@storybook/react";

import LemonCard from "./LemonCard";

const meta = {
  title: "Lemon / Card",
  component: LemonCard,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof LemonCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div className="p-6 max-w-xl">
      <LemonCard title="Investigation · NVDA Q4 risk model">
        <p className="text-sm leading-relaxed">
          Reading thirty-six analyst notes, four 10-Q filings, and a hand-picked
          set of subreddit threads. The trajectory should converge on a
          synthesis in roughly forty minutes.
        </p>
      </LemonCard>
    </div>
  ),
};

export const Elevations: Story = {
  render: () => (
    <div className="grid grid-cols-3 gap-6 p-6">
      <LemonCard elevation="z1" title="z1"><div>shallow</div></LemonCard>
      <LemonCard elevation="z2" title="z2"><div>default</div></LemonCard>
      <LemonCard elevation="z3" title="z3"><div>floating</div></LemonCard>
    </div>
  ),
};

export const Colours: Story = {
  render: () => (
    <div className="grid grid-cols-2 gap-6 p-6">
      <LemonCard colour="card"    title="card"   >ice-0 surface</LemonCard>
      <LemonCard colour="sun"     title="sun"    >sun fill — high attention</LemonCard>
      <LemonCard colour="aurora"  title="aurora" >aurora — AI-thinking</LemonCard>
      <LemonCard colour="glacial" title="glacial">subdued / inset</LemonCard>
      <LemonCard colour="ink"     title="ink"    >deepest plane</LemonCard>
    </div>
  ),
};

export const WithFooter: Story = {
  render: () => (
    <div className="p-6 max-w-xl">
      <LemonCard
        title="Synthesis ready"
        footer={
          <div className="flex justify-end gap-2 font-mono text-xs">
            <span>17 claims · 4 open questions</span>
          </div>
        }
      >
        <p className="text-sm leading-relaxed">
          The substrate has finished its recursive note-taking pass over the corpus.
          Highlight any passage in the result to chase it further.
        </p>
      </LemonCard>
    </div>
  ),
};
