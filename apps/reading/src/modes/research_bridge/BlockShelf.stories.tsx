import type { Meta, StoryObj } from "@storybook/react";

import { BlockShelf } from "./BlockShelf";
import { MOCK_BLOCKS } from "./mock_blocks";

const meta = {
  title: "Research Bridge / BlockShelf",
  component: BlockShelf,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof BlockShelf>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div className="max-w-md h-[600px] p-4"><BlockShelf blocks={MOCK_BLOCKS} /></div>
  ),
};

export const MultiSelect: Story = {
  render: () => (
    <div className="max-w-md h-[600px] p-4"><BlockShelf blocks={MOCK_BLOCKS} multiSelect /></div>
  ),
};

export const PreFilteredAnthropic: Story = {
  render: () => (
    <div className="max-w-md h-[600px] p-4">
      <BlockShelf blocks={MOCK_BLOCKS} initialSourceFilter={["anthropic"]} />
    </div>
  ),
};

export const EmptyState: Story = {
  render: () => (
    <div className="max-w-md h-[600px] p-4"><BlockShelf blocks={[]} /></div>
  ),
};

export const LargeShelf: Story = {
  render: () => {
    const big = Array.from({ length: 40 }).flatMap((_, i) =>
      MOCK_BLOCKS.map((b) => ({ ...b, document_id: `${b.document_id}-${i}` })),
    );
    return <div className="max-w-md h-[600px] p-4"><BlockShelf blocks={big} /></div>;
  },
};
