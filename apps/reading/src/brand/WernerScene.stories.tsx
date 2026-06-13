import type { Meta, StoryObj } from "@storybook/react";

import Werner from "./Werner";
import { wernerForScene, POSE_GAPS } from "./wernerSceneMap";
import { momentForTransition, fallbackBeat } from "./wernerMoments";
import type { SceneMood, DayPart, Weather } from "../scene/mood";

/**
 * WernerScene.stories — the AUTHORED scene-reactivity surface (ALC SPR-07).
 *
 * Werner's character is graded on INTENTIONALITY: every scene state authored,
 * the personality coherent. These stories make each authored state inspectable
 * in isolation (the co-located Storybook authorship the product-character
 * dimension rewards), and they double as the audit evidence for M1 (a pose for
 * every scene state) + M2 (the deterministic delight moments at transitions).
 *
 * Nothing here resembles or references any other product's mascot; Werner is
 * Antiek's own mark, graded for craft only.
 */
const meta = {
  title: "Brand / Werner / Scene reactivity",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const DAY_PARTS: readonly DayPart[] = ["dawn", "day", "dusk", "night"];
const WEATHERS: readonly Weather[] = ["clear", "snow"];

const SceneCell = ({ scene }: { scene: SceneMood }) => {
  const cue = wernerForScene(scene);
  const isGap = POSE_GAPS.some((g) => g.sceneKey === cue.sceneKey);
  return (
    <div className="flex flex-col items-center gap-2 rounded-hog border-edge border-sun bg-ice-0 p-5 dark:bg-charcoal-2">
      <div className="flex min-h-[88px] flex-1 items-center justify-center">
        <Werner scene={scene} size={72} label={`Werner ${cue.sceneKey}`} />
      </div>
      <div className="font-mono text-xs uppercase tracking-wider text-ink-soft dark:text-starlight">
        {cue.sceneKey}
      </div>
      <div className="font-mono text-[10px] text-ink-mute dark:text-moonlight">
        resting: {cue.mood}
        {isGap ? " · gap" : ""}
      </div>
      <p className="text-center font-serif text-[11px] leading-snug text-shadow-1 dark:text-moonlight">
        {cue.reason}
      </p>
    </div>
  );
};

/** M1 — a pose for EVERY scene state (4 dayparts × 2 weathers), each cue's
 *  rationale shown. The two states the app emits today (day|snow, night|snow)
 *  are live; the rest light up when SPR-06's phase drift emits them. */
export const SceneRestingPoses: Story = {
  // BLOCK-bodied render (mirrors DelightMoments). The CSF babel indexer chokes on
  // an EXPRESSION-bodied `render: () => ( <JSX/> )` in this file's cumulative
  // token context (ALC SPR-08, fixing inherited SPR-07 build-storybook break);
  // the JSX is unchanged — only the arrow-body shape.
  render: () => {
    return (
      <div className="min-h-screen bg-ice-2 p-8 dark:bg-space-2">
        <h1 className="mb-1 font-serif text-xl text-ink dark:text-bright">
          Werner — scene resting poses
        </h1>
        <p className="mb-6 max-w-2xl font-serif text-sm leading-relaxed text-shadow-1 dark:text-moonlight">
          Werner notices the weather he stands in. Every one of the eight scene
          states resolves to a sanctioned pose; where the pose set has no bespoke
          art, the cue falls back to the closest existing pose and the gap is
          recorded for a future art session (marked “gap”).
        </p>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {DAY_PARTS.flatMap((dayPart) =>
            WEATHERS.map((weather) => (
              <SceneCell key={`${dayPart}|${weather}`} scene={{ dayPart, weather }} />
            )),
          )}
        </div>
      </div>
    );
  },
};

const TransitionCell = ({
  from,
  to,
  label,
}: {
  from: SceneMood | null;
  to: SceneMood;
  label: string;
}) => {
  const m = momentForTransition(from, to);
  return (
    <div className="flex flex-col items-center gap-2 rounded-hog border-edge border-sun bg-ice-0 p-5 dark:bg-charcoal-2">
      <div className="flex min-h-[88px] flex-1 items-center justify-center">
        {/* The pose the beat flashes (or the resting pose if no beat). */}
        <Werner mood={m ? m.pose : wernerForScene(to).mood} size={72} label={label} />
      </div>
      <div className="font-mono text-xs uppercase tracking-wider text-ink-soft dark:text-starlight">
        {label}
      </div>
      <div className="font-mono text-[10px] text-ink-mute dark:text-moonlight">
        {m ? `${m.id} · ${m.durationMs}ms` : "no beat (settles quietly)"}
      </div>
      <p className="text-center font-serif text-[11px] leading-snug text-shadow-1 dark:text-moonlight">
        {m ? m.reason : "A change that earns no special beat — the resting cue is enough."}
      </p>
    </div>
  );
};

/** M2 — the deterministic delight moments, each at its exact trigger transition.
 *  All collapse to a static pose under reduced motion (the reducedPose field). */
export const DelightMoments: Story = {
  render: () => {
    const DAY: SceneMood = { dayPart: "day", weather: "snow" };
    const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };
    const DUSK: SceneMood = { dayPart: "dusk", weather: "snow" };
    const fb = fallbackBeat(NIGHT);
    return (
      <div className="min-h-screen bg-ice-2 p-8 dark:bg-space-2">
        <h1 className="mb-1 font-serif text-xl text-ink dark:text-bright">
          Werner — delight moments (scene transitions)
        </h1>
        <p className="mb-6 max-w-2xl font-serif text-sm leading-relaxed text-shadow-1 dark:text-moonlight">
          A beat fires only at a scene transition, when the reader’s eye is
          already on the changing world. Each is a one-shot, deterministic
          (driven by the state change, never a timer or random), and collapses to
          a static pose under reduced motion.
        </p>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <TransitionCell from={DAY} to={NIGHT} label="day → night" />
          <TransitionCell from={NIGHT} to={DAY} label="night → day" />
          <TransitionCell from={DAY} to={DUSK} label="→ dusk" />
          <div className="flex flex-col items-center gap-2 rounded-hog border-edge border-sun bg-ice-0 p-5 dark:bg-charcoal-2">
            <div className="flex min-h-[88px] flex-1 items-center justify-center">
              <Werner mood={fb.cue.mood} size={72} label="fallback" />
            </div>
            <div className="font-mono text-xs uppercase tracking-wider text-ink-soft dark:text-starlight">
              art missing
            </div>
            <div className="font-mono text-[10px] text-ink-mute dark:text-moonlight">
              {fb.id} · {fb.cue.mood}
            </div>
            <p className="text-center font-serif text-[11px] leading-snug text-shadow-1 dark:text-moonlight">
              {fb.reason}
            </p>
          </div>
        </div>
      </div>
    );
  },
};
