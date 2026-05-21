import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import ChaseSlideOver from "./ChaseSlideOver";

/**
 * ChaseSlideOver — right-side slide-over that lets the operator spawn
 * a child investigation from a highlighted excerpt. In S5 this becomes
 * a floating workspace panel instead of a slide-over.
 */
const meta = {
  title: "Loop 1 / ChaseSlideOver",
  component: ChaseSlideOver,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof ChaseSlideOver>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Closed: Story = {
  args: {
    open: false,
    spawnContext: "",
    parentInvestigationId: "inv-storybook-demo",
    onClose: () => {},
  },
};

export const Open: Story = {
  args: {
    open: true,
    spawnContext:
      "the gap between groups is a genuine difference in platform physics",
    parentInvestigationId: "inv-storybook-demo",
    onClose: () => alert("close"),
  },
};

export const Toggleable: Story = {
  render: () => {
    const Inner = () => {
      const [open, setOpen] = useState(false);
      return (
        <div className="p-10">
          <LemonButton variant="primary" onClick={() => setOpen(true)}>
            Open chase
          </LemonButton>
          <ChaseSlideOver
            open={open}
            spawnContext="Why does the gap between groups persist after circuit-depth normalization?"
            parentInvestigationId="inv-storybook-demo"
            onClose={() => setOpen(false)}
          />
        </div>
      );
    };
    return <Inner />;
  },
};
