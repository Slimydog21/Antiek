import type { Meta, StoryObj } from "@storybook/react";

import { ProceduralSky } from "./ProceduralSky";
import type { DayPart, SceneMood } from "../mood";
import { moodKey } from "../mood";

/**
 * ProceduralSky.stories — the SPR-05 mood-matrix, Storybook-visible (ALC SPR-09).
 *
 * The scene's procedural sky is the picture EVERY user sees (no Krea key, no
 * network — `ProceduralSky` is the always-on offline floor). SPR-05 M2 designed
 * a distinct atmosphere per dayPart ANCHOR (dawn / day / dusk / night): a 4-stop
 * sky ramp, a horizon glow, seeded stars at dusk+night, and three hazed peak
 * bands. Until now that designed mood-matrix was only inspectable through the
 * deterministic snapshot harness (`__matrix__/snapshot-matrix.test.tsx`) — never
 * in Storybook. These stories author each ANCHOR as a distinct named story so the
 * designed atmosphere per dayPart is inspectable in isolation, the co-located
 * Storybook authorship the product-character dimension rewards.
 *
 * DETERMINISM (the build-storybook + byte-stability contract): each story fixes
 * the scene_key via a literal `SceneMood` (the seeded path — `fieldSeed(moodKey)`
 * drives the ridge + star fields, exactly the seed the SPR-05 matrix harness
 * uses). ProceduralSky carries NO clock, NO rAF, NO Math.random / Date.now — it
 * is a pure function of `mood`, so the same mood renders byte-identical every
 * time. No story here reads a live clock or randomness in its render path.
 *
 * RENDER SHAPE: BLOCK-bodied render arrows only (the ALC SPR-08 build-storybook
 * escape lesson — the CSF babel indexer chokes on expression-bodied arrows in a
 * cumulative token context). The wrapper gives the `absolute inset-0` layer a
 * sized stage to fill.
 */
const meta = {
  title: "Scene / Layers / ProceduralSky",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

/** A sized stage for the full-bleed `absolute inset-0` sky layer, with the
 *  daypart + scene_key labelled so the inspected anchor is unambiguous. */
const SkyStage = ({ mood }: { mood: SceneMood }) => {
  return (
    <div className="bg-ink p-6">
      <div className="mb-2 font-mono text-xs uppercase tracking-wider text-starlight">
        ProceduralSky · {mood.dayPart} · scene_key {moodKey(mood)}
      </div>
      <div className="relative aspect-video w-full overflow-hidden rounded-hog">
        <ProceduralSky mood={mood} />
      </div>
    </div>
  );
};

/** Fixed scene_keys — one per dayPart anchor, weather pinned to the always-on
 *  snow motif so the seed (and thus the ridge + star fields) is byte-stable. */
const DAWN: SceneMood = { dayPart: "dawn", weather: "snow" };
const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const DUSK: SceneMood = { dayPart: "dusk", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };

/** Dawn anchor — cool glacial pre-light: dawn sky ramp + warm horizon glow, NO
 *  stars (hasStars is dusk/night only), cool glacial peak silhouettes. */
export const Dawn: Story = {
  render: () => {
    return <SkyStage mood={DAWN} />;
  },
};

/** Day anchor — the light state (the app emits this when the OS theme is light):
 *  the ice sky ramp, cool horizon glow, no stars, ice-ramp peaks. */
export const Day: Story = {
  render: () => {
    return <SkyStage mood={DAY} />;
  },
};

/** Dusk anchor — twilight: the dusk ramp + a seeded STAR field appears (dusk is
 *  the earlier of the two star anchors), twilight peaks a touch lighter than
 *  full night. A reserved transitional anchor SPR-06 can drift into. */
export const Dusk: Story = {
  render: () => {
    return <SkyStage mood={DUSK} />;
  },
};

/** Night anchor — the dark state (the app emits this when the OS theme is dark):
 *  the deepest sky ramp, a full seeded star field, charcoal/space peak bands. */
export const Night: Story = {
  render: () => {
    return <SkyStage mood={NIGHT} />;
  },
};

/** The full four-anchor mood-matrix side by side — the SPR-05 designed
 *  atmosphere across the whole dayPart axis, one diffable grid. Each cell is the
 *  same deterministic ProceduralSky at a fixed scene_key. */
export const MoodMatrix: Story = {
  render: () => {
    const anchors: SceneMood[] = [DAWN, DAY, DUSK, NIGHT];
    return (
      <div className="min-h-screen bg-ink p-8">
        <h1 className="mb-1 font-serif text-xl text-bright">
          ProceduralSky — dayPart mood matrix
        </h1>
        <p className="mb-6 max-w-2xl font-serif text-sm leading-relaxed text-moonlight">
          The atmosphere SPR-05 designed for each dayPart anchor — sky ramp,
          horizon glow, seeded stars (dusk + night), and hazed peak bands. Every
          cell is a deterministic render at a fixed scene_key; the same seed
          drives the ridge and star fields the matrix harness asserts byte-stable.
        </p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {anchors.map((mood) => (
            <div key={moodKey(mood)}>
              <div className="mb-2 font-mono text-xs uppercase tracking-wider text-starlight">
                {mood.dayPart} · {moodKey(mood)}
              </div>
              <div className="relative aspect-video w-full overflow-hidden rounded-hog">
                <ProceduralSky mood={mood} />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  },
};
