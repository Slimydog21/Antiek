import type { Meta, StoryObj } from "@storybook/react";

import type { InvestigationSummary } from "../../lib/api";
import { ChartRoomFrame, ResearchLineageBoard } from "./MyResearch";

const FIXED_NOW_MS = Date.parse("2026-07-15T12:00:00Z");

const ROOT: InvestigationSummary = {
  investigation_id: "inv-root-001",
  question: "What are the economic effects of deep-sea mining on Pacific Island nations?",
  status: "completed",
  started_at: "2026-07-10T09:00:00Z",
  completed_at: "2026-07-10T09:45:00Z",
  cost_usd_total: 0.1234,
  parent_investigation_id: null,
};

const CHILD: InvestigationSummary = {
  investigation_id: "inv-child-001",
  question: "How does deep-sea mining affect tuna fisheries in the EEZ?",
  status: "in_progress",
  started_at: "2026-07-10T09:50:00Z",
  completed_at: null,
  cost_usd_total: 0.0456,
  parent_investigation_id: ROOT.investigation_id,
  spawned_by_daemon: true,
};

const meta = {
  title: "ResearchWorkstation / MyResearch / ChartRoom",
  component: ChartRoomFrame,
  parameters: { layout: "fullscreen", lostpixel: { waitBeforeScreenshot: 300 } },
  decorators: [
    (Story) => (
      <main className="h-screen bg-ice-0 text-ink dark:bg-charcoal-2 dark:text-bright">
        <Story />
      </main>
    ),
  ],
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof ChartRoomFrame>;

export default meta;
type Story = StoryObj<typeof meta>;

function Summary({ running, done }: { running: number; done: number }) {
  return (
    <div className="space-y-4 rounded-hog-lg border border-rule bg-ice-0/95 p-5 shadow-z1">
      <p className="font-mono text-[12px] text-shadow-1" aria-live="polite">
        {running} running · {done} done · $0.1690 spent so far
      </p>
      <div className="flex flex-wrap gap-3">
        <button type="button" className="rounded-hog bg-ink px-3 py-2 font-mono text-[12px] text-ice-0">
          Start a research
        </button>
        <button type="button" className="rounded-hog border border-rule bg-ice-0 px-3 py-2 font-mono text-[12px] text-ink">
          Launch several at once
        </button>
      </div>
    </div>
  );
}

export const Ready: Story = {
  render: () => (
    <ChartRoomFrame fixture>
      <div className="space-y-5">
        <Summary running={1} done={1} />
        <ResearchLineageBoard investigations={[ROOT, CHILD]} nowMs={FIXED_NOW_MS} />
      </div>
    </ChartRoomFrame>
  ),
};

export const Loading: Story = {
  render: () => (
    <ChartRoomFrame fixture>
      <div className="rounded-hog-lg border border-rule bg-ice-0/95 p-5 shadow-z1">
        <p role="status" className="font-serif text-sm italic text-shadow-1">Loading…</p>
      </div>
    </ChartRoomFrame>
  ),
};

export const Empty: Story = {
  render: () => (
    <ChartRoomFrame fixture>
      <div className="space-y-5">
        <Summary running={0} done={0} />
        <div className="rounded-hog-lg border border-rule bg-ice-0/95 p-5 shadow-z1">
          <p className="font-serif text-sm text-ink">No research yet.</p>
          <p className="mt-1 font-mono text-[11px] text-shadow-1">Add a model provider, then start the first research.</p>
        </div>
      </div>
    </ChartRoomFrame>
  ),
};

export const NeedsAttention: Story = {
  render: () => (
    <ChartRoomFrame fixture>
      <div role="alert" className="rounded-hog-lg border border-emperor bg-ice-0/95 p-5 shadow-z1">
        <p className="font-serif text-sm text-emperor">Couldn’t load your research — the engine reported a problem. Try again.</p>
        <button type="button" className="mt-3 rounded-hog border border-rule px-3 py-2 font-mono text-[12px]">Try again</button>
      </div>
    </ChartRoomFrame>
  ),
};

export const Standalone: Story = {
  render: () => (
    <ChartRoomFrame fixture>
      <ResearchLineageBoard investigations={[ROOT]} nowMs={FIXED_NOW_MS} />
    </ChartRoomFrame>
  ),
};

export const ProductionRaster: Story = {
  parameters: { lostpixel: { disable: true } },
  render: () => (
    <ChartRoomFrame>
      <div className="space-y-5">
        <Summary running={1} done={1} />
        <ResearchLineageBoard investigations={[ROOT, CHILD]} nowMs={FIXED_NOW_MS} />
      </div>
    </ChartRoomFrame>
  ),
};

export const OverflowStress: Story = {
  parameters: { lostpixel: { disable: true } },
  render: () => (
    <ChartRoomFrame fixture>
      <ResearchLineageBoard
        nowMs={FIXED_NOW_MS}
        investigations={Array.from({ length: 30 }, (_, index) => ({
          ...ROOT,
          investigation_id: `inv-overflow-${String(index).padStart(2, "0")}`,
          question: `Overflow research ${index + 1}: preserve access to every row`,
        }))}
      />
    </ChartRoomFrame>
  ),
};
