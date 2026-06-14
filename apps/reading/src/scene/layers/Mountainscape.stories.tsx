import type { Meta, StoryObj } from "@storybook/react";

import { Mountainscape, PLANE_DEPTHS } from "./Mountainscape";
import type { SceneMood } from "../mood";
import { moodKey } from "../mood";

/**
 * Mountainscape.stories — the SPR-05 depth-plane composition, Storybook-visible
 * (ALC SPR-09).
 *
 * Mountainscape is the foreground DEPTH substrate (SPR-05 M4): three seeded ridge
 * PLANES (far / mid / near) with an aerial-perspective haze veil between them, so
 * distance reads through value + saturation recession. SPR-06 lights up each
 * plane's typed `PlaneSeam` for the parallax breath; this STORY renders the STATIC
 * composed frame (no seams supplied ⇒ the designed reduced-motion pose), exactly
 * what the layer paints with no clock driving it.
 *
 * DETERMINISM: every plane's ridge is pure `makeRidge(fieldSeed(moodKey) ^ salt)`
 * and memoized on the seed — same mood → byte-identical planes. No clock, no
 * rAF, no Math.random / Date.now in the render path. Each story fixes the
 * scene_key via a literal SceneMood, so the composition is byte-stable.
 *
 * RENDER SHAPE: BLOCK-bodied render arrows only (the SPR-08 build-storybook
 * escape lesson). The wrapper sizes the `absolute inset-0` layer.
 */
const meta = {
  title: "Scene / Layers / Mountainscape",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };

const DepthStage = ({ mood }: { mood: SceneMood }) => {
  return (
    <div className="bg-ink p-6">
      <div className="mb-2 font-mono text-xs uppercase tracking-wider text-starlight">
        Mountainscape · {mood.dayPart} · scene_key {moodKey(mood)} · depths{" "}
        {PLANE_DEPTHS.join(" / ")}
      </div>
      {/* A light sky behind so the depth planes' value recession reads against a
          backdrop (in production ProceduralSky sits behind; here a neutral wash
          isolates the depth layer). */}
      <div className="relative aspect-video w-full overflow-hidden rounded-hog bg-ice-2 dark:bg-space-2">
        <Mountainscape mood={mood} />
      </div>
    </div>
  );
};

/** Day composition — far plane lightest + most-hazed (recedes), near plane
 *  darkest + un-veiled (advances). The static frame, no parallax seams. */
export const DayComposition: Story = {
  render: () => {
    return <DepthStage mood={DAY} />;
  },
};

/** Night composition — the same three-plane recession in the night value family
 *  (charcoal far → space near). Designed depth holds across the dayPart axis. */
export const NightComposition: Story = {
  render: () => {
    return <DepthStage mood={NIGHT} />;
  },
};
