import type { Meta, StoryObj } from "@storybook/react";

import { PenguinMascot } from "../../shell/PenguinMascot";
import Home from "./Home";

/**
 * Home (SPR-12 M1) — the unified branded front door.
 *
 * One branded statement of what Antiek is, four equal doors (one click into
 * each surface), biographies featured. The knowledge-home artwork (Cycle 7)
 * sits behind the GlassSurface as a decorative atmospheric layer.
 *
 * Visual baseline coverage: the full home, its exact narrow crop, and its
 * production composition with the independent station mascot.
 */
const meta = {
  title: "Home / Unified home (SPR-12)",
  component: Home,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof Home>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div className="h-screen w-screen">
      <Home />
    </div>
  ),
};

/** The exact narrow aperture used to judge the authored 24% workbench focal
 * point. LostPixel captures this fixed mobile frame at every CI breakpoint. */
export const MobileCrop: Story = {
  render: () => (
    <div className="h-[844px] w-[390px] overflow-hidden">
      <Home />
    </div>
  ),
};

/** Production composition proof: the environment contains no baked mascot;
 * the one interactive shell-level Werner remains independently mounted. */
export const WithStationMascot: Story = {
  render: () => (
    <div className="relative h-screen w-screen overflow-hidden">
      <Home />
      <PenguinMascot />
    </div>
  ),
};
