import type { Meta, StoryObj } from "@storybook/react";

import { TwinNotesPanel } from "./TwinNotesPanel";
import type { TwinDocument } from "./twinDocument";

const liveTwin: TwinDocument = {
  id: "twin-story-live",
  parentAssetId: "doc-story",
  insights: [
    {
      id: "i1",
      text: "The recursive twin compounds search quality when every asset carries open questions.",
    },
    {
      id: "i2",
      text: "HTML-native delivery keeps the twin editable by agents without PDF layout drift.",
    },
  ],
  questions: [
    {
      id: "q1",
      text: "What evidence would falsify universal twin coverage across the library?",
      open: true,
    },
    {
      id: "q2",
      text: "How should budget gates allocate twin-generation versus deep-research spend?",
      open: true,
    },
  ],
  authority: "advisory",
  isTwin: true,
  status: "ready",
};

const meta = {
  title: "Loop 2 / Twin notes companion",
  component: TwinNotesPanel,
  parameters: { layout: "padded" },
  decorators: [
    (Story) => (
      <main className="min-h-[480px] bg-ice-2 p-6 dark:bg-space-2">
        <h1 className="sr-only">Twin notes companion</h1>
        <div className="mx-auto max-w-md">
          <Story />
        </div>
      </main>
    ),
  ],
} satisfies Meta<typeof TwinNotesPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Labeled demo fixture — offline UX honesty when no live twin. */
export const DemoFixture: Story = {
  args: {
    parentAssetId: "doc-demo",
    allowDemo: true,
  },
};

/** Live twin prop path (data-is-demo=false). */
export const LiveTwin: Story = {
  args: {
    parentAssetId: "doc-story",
    twin: liveTwin,
    allowDemo: false,
  },
};

/** Empty honesty when demo is disabled and no twin is provided. */
export const EmptyNoDemo: Story = {
  args: {
    parentAssetId: "doc-empty",
    allowDemo: false,
  },
};
