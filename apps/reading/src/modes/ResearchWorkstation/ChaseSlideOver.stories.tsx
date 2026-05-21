import type { Meta, StoryObj } from "@storybook/react";

import ChaseSlideOver from "./ChaseSlideOver";

/**
 * Chase panel — pre-fills a textarea with a highlighted excerpt, lets
 * the operator refine it, spawns a child investigation. As of S5 this
 * is a workspace floating panel (PanelKind = "Chase"), not a slide-over,
 * so the stories render the inner content directly inside a panel-like
 * box. The wrapper just simulates the panel-frame.
 */
const meta = {
  title: "Loop 1 / Chase",
  component: ChaseSlideOver,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof ChaseSlideOver>;

export default meta;
type Story = StoryObj<typeof meta>;

function PanelFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-[460px] h-[480px] bg-ice-0 dark:bg-charcoal-2 border-edge border-sun rounded-hog shadow-z2 dark:shadow-z2-night overflow-hidden">
      {children}
    </div>
  );
}

export const Default: Story = {
  render: () => (
    <PanelFrame>
      <ChaseSlideOver
        spawnContext="the gap between groups is a genuine difference in platform physics"
        parentInvestigationId="inv-storybook-demo"
      />
    </PanelFrame>
  ),
};

export const LongExcerpt: Story = {
  render: () => (
    <PanelFrame>
      <ChaseSlideOver
        spawnContext="Why does the gap between groups persist after circuit-depth normalisation? Are the published 2024-2025 numbers comparable at all, or does the gate-set choice make a head-to-head benchmark impossible without a shared decomposition?"
        parentInvestigationId="inv-storybook-demo"
      />
    </PanelFrame>
  ),
};
