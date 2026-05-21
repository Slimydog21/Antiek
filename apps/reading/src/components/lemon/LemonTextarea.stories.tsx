import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";

import LemonTextarea from "./LemonTextarea";

const meta = {
  title: "Lemon / Textarea",
  component: LemonTextarea,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof LemonTextarea>;

export default meta;
type Story = StoryObj<typeof meta>;

export const AutoGrow: Story = {
  render: () => {
    const Inner = () => {
      const [v, setV] = useState("Type and watch the textarea grow…");
      return (
        <div className="p-6 max-w-xl">
          <LemonTextarea
            value={v}
            onChange={(e) => setV(e.target.value)}
            placeholder="Ask anything…"
            onSubmit={(val) => alert(`Submitted (${val.length} chars):\n${val}`)}
            minRows={2}
            maxRows={10}
          />
          <p className="mt-2 text-xs text-shadow-1 dark:text-moonlight font-mono">
            ⌘ ↵ to submit. {v.length} characters.
          </p>
        </div>
      );
    };
    return <Inner />;
  },
};

export const Empty: Story = {
  render: () => (
    <div className="p-6 max-w-xl">
      <LemonTextarea placeholder="What do you want to research?" />
    </div>
  ),
};
