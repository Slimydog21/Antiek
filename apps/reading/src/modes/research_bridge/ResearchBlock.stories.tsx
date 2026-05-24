import type { Meta, StoryObj } from "@storybook/react";

import { ResearchBlock } from "./ResearchBlock";
import { MOCK_BLOCKS } from "./mock_blocks";

const meta = {
  title: "Research Bridge / ResearchBlock",
  component: ResearchBlock,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof ResearchBlock>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Mini: Story = {
  render: () => (
    <div className="flex flex-col gap-2 max-w-md p-4">
      {MOCK_BLOCKS.map((b) => <ResearchBlock key={b.document_id} block={b} size="mini" />)}
    </div>
  ),
};

export const Standard: Story = {
  render: () => (
    <div className="flex flex-col gap-3 max-w-md p-4">
      {MOCK_BLOCKS.map((b) => <ResearchBlock key={b.document_id} block={b} size="standard" />)}
    </div>
  ),
};

export const Expanded: Story = {
  render: () => (
    <div className="flex flex-col gap-3 max-w-2xl p-4">
      {MOCK_BLOCKS.slice(0, 2).map((b) => (
        <ResearchBlock
          key={b.document_id}
          block={{
            ...b,
            preview_text:
              "The market for on-policy reinforcement-learning training of code-completion agents has fragmented into three identifiable layers since mid-2024.",
          }}
          size="expanded"
        />
      ))}
    </div>
  ),
};

export const Selected: Story = {
  render: () => (
    <div className="flex flex-col gap-2 max-w-md p-4">
      <ResearchBlock block={MOCK_BLOCKS[0]} size="standard" selected />
    </div>
  ),
};
