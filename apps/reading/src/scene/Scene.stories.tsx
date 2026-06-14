import type { Meta, StoryObj } from "@storybook/react";

import { Scene } from "./Scene";
import type { SceneMood } from "./mood";
import { moodKey } from "./mood";

/**
 * Scene.stories — the integrated procedural floor, reducedMotion-FROZEN
 * (ALC SPR-09).
 *
 * Scene composes the whole living mountainscape: ProceduralSky + backdrop ridge
 * (Peaks), the Mountainscape depth planes, Clouds, Snow, and the scenery
 * PenguinJourney, back to front. These stories render the full composition with
 * `reducedMotion` forced — the reduced-motion degradation rung, where the scene
 * clock freezes (one frame at FROZEN_T), the canvases paint once, parallax is
 * disabled, and CSS animations pause. That makes the integrated floor
 * deterministic and Storybook-renderable as a single static frame.
 *
 * The `mood` prop is supplied directly (not derived from the OS theme) so each
 * story pins a representative scene_key. No Krea fetcher is injected, so
 * KreaArtLayer renders nothing — the always-on PROCEDURAL floor, the picture
 * every keyless user actually sees.
 *
 * NOTE: a separate Werner-on-scene authoring surface already exists
 * (`brand/WernerScene.stories.tsx`, SPR-07) and `WorkspaceDemo` carries a
 * (filterShot-excluded, nondeterministic) live scene — this is the SCENE-LAYER
 * composite at the procedural floor, distinct from both.
 *
 * RENDER SHAPE: BLOCK-bodied render arrows only (the SPR-08 build-storybook
 * escape lesson). The wrapper sizes the `absolute inset-0` Scene root.
 */
const meta = {
  title: "Scene / Composite",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };

const SceneStage = ({ mood }: { mood: SceneMood }) => {
  return (
    <div className="bg-ink p-6">
      <div className="mb-2 font-mono text-xs uppercase tracking-wider text-starlight">
        Scene (procedural floor · reducedMotion-frozen) · {mood.dayPart} ·
        scene_key {moodKey(mood)}
      </div>
      <div className="relative aspect-video w-full overflow-hidden rounded-hog">
        {/* mood pinned + reducedMotion forced ⇒ deterministic static frame;
            no fetchScene ⇒ KreaArtLayer paints nothing (the procedural floor). */}
        <Scene mood={mood} reducedMotion />
      </div>
    </div>
  );
};

/** Day floor — the full procedural composition at the day scene_key, frozen. */
export const DayFloor: Story = {
  render: () => {
    return <SceneStage mood={DAY} />;
  },
};

/** Night floor — the full composition at the night scene_key (stars + dimmer
 *  clouds/snow), frozen. */
export const NightFloor: Story = {
  render: () => {
    return <SceneStage mood={NIGHT} />;
  },
};
