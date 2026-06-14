import type { Meta, StoryObj } from "@storybook/react";

import { PenguinJourney } from "./PenguinJourney";
import type { SceneMood } from "../mood";
import { moodKey } from "../mood";

/**
 * PenguinJourney.stories — the scenery penguin, Storybook-visible (ALC SPR-09).
 *
 * PenguinJourney is the small decorative penguin SILHOUETTE that walks the lower
 * horizon toward the unknown (SPR-04 M3) — DELIBERATELY distinct from the
 * interactive <PenguinMascot/> (it never reacts; pointer-events-none, aria-hidden).
 * Its motion is a pure CSS keyframe (`akb-penguin-journey` + `akb-penguin-bob`
 * in scene.css), so the silhouette + colours are a pure function of `mood` — the
 * markup is byte-stable regardless of animation phase. The walk loops via CSS and
 * pauses for free under the `motion-reduce:` variant (Storybook honours the OS
 * reduce-motion setting via preview.tsx's motion.css).
 *
 * The penguin colour shifts by dayPart (a darker shape by day, a faint one by
 * night), so the two stories author the two visible silhouette states.
 *
 * DETERMINISM: no JS clock, no rAF, no Math.random / Date.now in the render path
 * — the only motion is declarative CSS off the design-token motion vocabulary.
 * Each story fixes the mood via a literal SceneMood.
 *
 * RENDER SHAPE: BLOCK-bodied render arrows only (the SPR-08 build-storybook
 * escape lesson). The wrapper sizes the `absolute inset-x-0 bottom-0` band.
 */
const meta = {
  title: "Scene / Layers / PenguinJourney",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };

const PenguinStage = ({ mood }: { mood: SceneMood }) => {
  return (
    <div className="bg-ink p-6">
      <div className="mb-2 font-mono text-xs uppercase tracking-wider text-starlight">
        PenguinJourney (scenery) · {mood.dayPart} · scene_key {moodKey(mood)}
      </div>
      {/* A ground band so the penguin (anchored to the lower third) is visible;
          the layer itself is the bottom-third strip it journeys across. */}
      <div className="relative h-64 w-full overflow-hidden rounded-hog bg-glacial-2 dark:bg-charcoal-1">
        <PenguinJourney mood={mood} />
      </div>
    </div>
  );
};

/** Day silhouette — the scenery penguin reads as a darker shadow shape against
 *  the day ground. The CSS walk loops (pauses under reduced-motion). */
export const DaySilhouette: Story = {
  render: () => {
    return <PenguinStage mood={DAY} />;
  },
};

/** Night silhouette — the same penguin in its faint night-coat colouring, so the
 *  shape stays legible against the darker night ground. */
export const NightSilhouette: Story = {
  render: () => {
    return <PenguinStage mood={NIGHT} />;
  },
};
