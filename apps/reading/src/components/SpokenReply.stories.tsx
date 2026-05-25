import type { Meta, StoryObj } from "@storybook/react";

import SpokenReply from "./SpokenReply";

/**
 * SpokenReply in a rabbit-hole reply. The text is always shown; the
 * "Listen" control is the audio option. (Storybook has no TTS backend, so
 * clicking surfaces the graceful 503 "unavailable" state — which is
 * exactly what a reader sees when the operator key isn't set.)
 */
const meta = {
  title: "Read / SpokenReply",
  component: SpokenReply,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof SpokenReply>;

export default meta;
type Story = StoryObj<typeof meta>;

export const InAReply: Story = {
  render: () => (
    <div className="max-w-lg space-y-2">
      <p className="font-serif text-[15px] leading-[1.7] text-ink dark:text-bright">
        The passage echoes Seneca: that the obstacle to a tranquil mind is
        not the event but our judgement of it. Read against the surrounding
        chapter, the author is making the Stoic move explicit.
      </p>
      <SpokenReply text="The passage echoes Seneca: that the obstacle to a tranquil mind is not the event but our judgement of it." />
    </div>
  ),
};
