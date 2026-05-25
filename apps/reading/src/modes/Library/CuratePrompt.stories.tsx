import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";

import CuratePrompt from "./CuratePrompt";

/**
 * Prompt-to-curate input (Read SPR-04). The reader describes what they
 * want to read; the shelf re-ranks (servable books only).
 */
const meta = {
  title: "Read / CuratePrompt",
  component: CuratePrompt,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof CuratePrompt>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Idle: Story = {
  args: { onCurate: () => {}, onClear: () => {}, active: false },
};

export const ActiveWithClear: Story = {
  render: () => {
    const Demo = () => {
      const [active, setActive] = useState(true);
      return (
        <CuratePrompt onCurate={() => setActive(true)} onClear={() => setActive(false)} active={active} />
      );
    };
    return <Demo />;
  },
};

export const Busy: Story = {
  args: { onCurate: () => {}, onClear: () => {}, active: false, busy: true },
};
