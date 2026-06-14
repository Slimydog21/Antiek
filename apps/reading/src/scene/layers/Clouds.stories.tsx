import type { Meta, StoryObj } from "@storybook/react";

import { Clouds } from "./Clouds";
import type { SceneMood } from "../mood";
import { moodKey } from "../mood";

/**
 * Clouds.stories — the parallax cloud canvas, FROZEN-frame (ALC SPR-09).
 *
 * Clouds is a Canvas 2D layer of soft radial blobs. In production it paints every
 * frame off the single scene clock; under reduced-motion `subscribeSceneClock`
 * emits ONE frame at FROZEN_T and never loops. These stories pass
 * `reducedMotion` so the layer paints exactly that single static cloudscape — no
 * rAF, no loop, byte-stable: the cloud LAYOUT is `makeClouds(fieldSeed(moodKey))`
 * (deterministic) and the only time term (`cloudX(c, FROZEN_T, W)`) is evaluated
 * at the fixed FROZEN_T, so the frozen frame is the same every render.
 *
 * Canvas DOES render in Storybook (a real browser, unlike jsdom where the layer
 * is blank) — so the frozen cloudscape is genuinely visible here.
 *
 * RENDER SHAPE: BLOCK-bodied render arrows only (the SPR-08 build-storybook
 * escape lesson). The wrapper sizes the `absolute inset-0` canvas.
 */
const meta = {
  title: "Scene / Layers / Clouds",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };

const CloudStage = ({ mood }: { mood: SceneMood }) => {
  return (
    <div className="bg-ink p-6">
      <div className="mb-2 font-mono text-xs uppercase tracking-wider text-starlight">
        Clouds (frozen @ FROZEN_T) · {mood.dayPart} · scene_key {moodKey(mood)}
      </div>
      {/* A sky wash behind so the soft cloud blobs read; the canvas is the
          full-bleed `absolute inset-0` layer painting one frozen frame. */}
      <div className="relative aspect-video w-full overflow-hidden rounded-hog bg-glacial-1 dark:bg-space-1">
        <Clouds mood={mood} reducedMotion />
      </div>
    </div>
  );
};

/** Day clouds — the frozen cloudscape at the day mood (the cloud alpha is the
 *  day value); the deterministic single frame at FROZEN_T. */
export const DayFrozen: Story = {
  render: () => {
    return <CloudStage mood={DAY} />;
  },
};

/** Night clouds — the same seeded cloud band at the night mood (dimmer cloud
 *  alpha), frozen at FROZEN_T. */
export const NightFrozen: Story = {
  render: () => {
    return <CloudStage mood={NIGHT} />;
  },
};
