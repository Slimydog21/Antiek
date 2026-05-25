import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";

import TocPanel from "./TocPanel";
import type { TocItem } from "../../api/books";

const toc: TocItem[] = [
  { title: "Book I", page_index: 0, level: 0 },
  { title: "1. The discipline of perception", page_index: 2, level: 1 },
  { title: "2. The discipline of action", page_index: 14, level: 1 },
  { title: "Book II", page_index: 40, level: 0 },
  { title: "An unresolvable bookmark", page_index: null, level: 1 },
];

const meta = {
  title: "Read / TocPanel",
  component: TocPanel,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof TocPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Interactive: clicking an entry jumps; an unresolvable bookmark is shown
 * disabled (honest about what the PDF outline gave us). */
export const Nested: Story = {
  render: () => {
    const Demo = () => {
      const [page, setPage] = useState(2);
      return (
        <div className="w-64">
          <TocPanel toc={toc} currentPageIndex={page} onJump={setPage} />
        </div>
      );
    };
    return <Demo />;
  },
};

export const Empty: Story = {
  args: { toc: [], currentPageIndex: 0, onJump: () => {} },
};
