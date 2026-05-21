import type { Meta, StoryObj } from "@storybook/react";

import InvestigationSidebar from "./InvestigationSidebar";

/**
 * InvestigationSidebar — left dock content in ResearchWorkstation.
 *
 * This component takes NO props; it consumes `useInvestigationList` +
 * `useInvestigationTree`, which both fetch from the live API. Without
 * an MSW (mock-service-worker) layer in Storybook, this story will
 * render an empty state when there is no backend running, or the live
 * data when there is. That is the expected behaviour for now.
 *
 * Tracked in STORYBOOK.md as a hook-coupled known gap; an MSW pass is
 * a S11 (a11y + responsive + reduced-motion) follow-up.
 */
const meta = {
  title: "Loop 1 / InvestigationSidebar",
  component: InvestigationSidebar,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof InvestigationSidebar>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Default render — will show the empty state when no backend is reachable.
 * That's the right thing to see in Storybook isolation. Wiring MSW for
 * full fixture-driven rendering is tracked separately.
 */
export const Default: Story = {
  render: () => (
    <div className="w-[320px] h-screen bg-ice-2 dark:bg-space-2 border-r-edge border-sun">
      <InvestigationSidebar />
    </div>
  ),
};
