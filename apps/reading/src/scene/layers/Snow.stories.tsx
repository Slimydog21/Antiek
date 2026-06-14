import type { Meta, StoryObj } from "@storybook/react";

import { Snow } from "./Snow";
import type { SceneMood } from "../mood";
import { moodKey } from "../mood";

/**
 * Snow.stories — the wind-driven snow canvas, FROZEN-frame (ALC SPR-09).
 *
 * Snow is a Canvas 2D flurry (SNOW_COUNT flakes, the always-on Herzog Antarctic
 * motif). In production it paints every frame off the single scene clock; under
 * reduced-motion `subscribeSceneClock` emits ONE frame at FROZEN_T and stops.
 * These stories pass `reducedMotion` so the layer paints exactly that single
 * static flurry — no rAF, no loop. Byte-stable: the flake SET is
 * `makeSnow(fieldSeed(moodKey))` (deterministic) and every flake's position is
 * `snowAt(f, FROZEN_T, …)`, evaluated at the fixed FROZEN_T, so the frozen frame
 * is identical every render.
 *
 * Canvas DOES render in Storybook (a real browser) — so the frozen flurry is
 * genuinely visible here (it is blank only in jsdom, where the layer no-ops).
 *
 * RENDER SHAPE: BLOCK-bodied render arrows only (the SPR-08 build-storybook
 * escape lesson). The wrapper sizes the `absolute inset-0` canvas.
 */
const meta = {
  title: "Scene / Layers / Snow",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };

const SnowStage = ({ mood }: { mood: SceneMood }) => {
  return (
    <div className="bg-ink p-6">
      <div className="mb-2 font-mono text-xs uppercase tracking-wider text-starlight">
        Snow (frozen @ FROZEN_T) · {mood.dayPart} · scene_key {moodKey(mood)}
      </div>
      {/* A darker wash behind so the light flakes read; the canvas is the
          full-bleed `absolute inset-0` layer painting one frozen frame. */}
      <div className="relative aspect-video w-full overflow-hidden rounded-hog bg-shadow-1 dark:bg-space-2">
        <Snow mood={mood} reducedMotion />
      </div>
    </div>
  );
};

/** Day flurry — the frozen snow field at the day mood (day snow alpha); the
 *  deterministic single frame at FROZEN_T. */
export const DayFrozen: Story = {
  render: () => {
    return <SnowStage mood={DAY} />;
  },
};

/** Night flurry — the same seeded flake set at the night mood, frozen at
 *  FROZEN_T. */
export const NightFrozen: Story = {
  render: () => {
    return <SnowStage mood={NIGHT} />;
  },
};
