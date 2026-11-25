import type { ReactNode } from "react";
import type { Meta, StoryObj } from "@storybook/react";

import ZenHome from "./ZenHome";

/**
 * ZenHome (FFX-KPA SPR-03) — the research door as one box: type, speak,
 * drop, or talk it through. Day and night stills for the visual baseline;
 * the SPR-04 switch mounts in the top-right slot (shown here with a
 * stand-in so the slot's position is pinned before the switch exists).
 */
const meta = {
  title: "Home / Zen home (FFX-KPA SPR-03)",
  component: ZenHome,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof ZenHome>;

export default meta;
type Story = StoryObj<typeof meta>;

const frame = (node: ReactNode) => <div className="h-screen w-screen bg-ice-2 dark:bg-space-2">{node}</div>;

export const Day: Story = { render: () => frame(<ZenHome />), globals: { theme: "light" } };
export const Night: Story = { render: () => frame(<ZenHome />), globals: { theme: "dark" } };
export const WithSwitchSlot: Story = {
  render: () =>
    frame(
      <ZenHome
        switchSlot={
          <span className="rounded-hog border border-rule px-2 py-1 text-xs font-sans text-ink dark:text-bright">
            switch (SPR-04)
          </span>
        }
      />,
    ),
  globals: { theme: "light" },
};
