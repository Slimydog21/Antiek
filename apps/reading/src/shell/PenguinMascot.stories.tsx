import type { Meta, StoryObj } from "@storybook/react";

import { PenguinMascot } from "./PenguinMascot";

/**
 * PenguinMascot (SPR-12 M3) — the floating project home.
 *
 * The mascot positions itself `fixed` over the whole app, so the stories
 * give it a full-bleed surface to float over. Visual baselines here cover
 * the mark's resting appearance in light + dark (the toolbar theme switch
 * drives the dark frame). The interaction model (click→float, drag,
 * double-click→open, idle wander, reduced-motion-still) is asserted in
 * PenguinMascot.test.tsx — the deterministic substitute for the lost-pixel
 * interaction snapshot the spec calls for.
 */
const meta = {
  title: "Shell / PenguinMascot (SPR-12)",
  component: PenguinMascot,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof PenguinMascot>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The mascot at rest over a blank surface — the logo-fix payoff is visible
 *  here too: no white box around the penguin on either theme. */
export const Resting: Story = {
  render: () => (
    <div className="h-screen w-screen bg-ice-2 dark:bg-space-2">
      <PenguinMascot />
    </div>
  ),
};
