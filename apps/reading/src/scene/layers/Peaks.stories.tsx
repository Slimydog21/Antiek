import type { Meta, StoryObj } from "@storybook/react";

import { Peaks } from "./Peaks";
import type { SceneMood } from "../mood";
import { moodKey } from "../mood";

/**
 * Peaks.stories — the seeded backdrop ridge silhouettes, Storybook-visible
 * (ALC SPR-09).
 *
 * Peaks renders ProceduralSky (the atmosphere + backdrop ridge bands) and adds
 * BOUNDED pointer parallax. These stories render Peaks `frozen` — the same path
 * the Scene takes under reduced-motion: parallax is disabled and the bands sit at
 * ZERO shift, a static composed frame. That makes the seeded ridge silhouettes
 * byte-stable and Storybook-renderable (the pointer-driven path never engages, so
 * no rAF / no live input in the story render).
 *
 * DETERMINISM: the ridge geometry is pure `makeRidge(fieldSeed(moodKey))` inside
 * ProceduralSky, memoized on the seed; `frozen` drops the pointer parallax
 * entirely. Same mood → byte-identical silhouettes. No clock, no Math.random.
 *
 * RENDER SHAPE: BLOCK-bodied render arrows only (the SPR-08 build-storybook
 * escape lesson). The wrapper sizes the `absolute inset-0` layer.
 */
const meta = {
  title: "Scene / Layers / Peaks",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };

const PeaksStage = ({ mood }: { mood: SceneMood }) => {
  return (
    <div className="bg-ink p-6">
      <div className="mb-2 font-mono text-xs uppercase tracking-wider text-starlight">
        Peaks (frozen · no parallax) · {mood.dayPart} · scene_key {moodKey(mood)}
      </div>
      <div className="relative aspect-video w-full overflow-hidden rounded-hog">
        {/* frozen ⇒ the reduced-motion path: zero shift, static seeded ridge. */}
        <Peaks mood={mood} frozen />
      </div>
    </div>
  );
};

/** Day ridge — the seeded backdrop bands over the day atmosphere, frozen (the
 *  static reduced-motion frame, no pointer parallax). */
export const DayRidge: Story = {
  render: () => {
    return <PeaksStage mood={DAY} />;
  },
};

/** Night ridge — the same seeded silhouettes under the night atmosphere (stars
 *  paint here via ProceduralSky), frozen. */
export const NightRidge: Story = {
  render: () => {
    return <PeaksStage mood={NIGHT} />;
  },
};
