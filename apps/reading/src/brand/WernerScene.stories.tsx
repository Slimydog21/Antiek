import type { Meta, StoryObj } from "@storybook/react";

import Werner from "./Werner";
import { fallbackBeat, momentForTransition } from "./wernerMoments";
import { POSE_GAPS, wernerForScene } from "./wernerSceneMap";
import type { DayPart, SceneMood, Weather } from "../scene/mood";

const meta = {
  title: "Brand / Werner / Scene",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const DAY_PARTS = ["dawn", "day", "dusk", "night"] satisfies readonly DayPart[];
const WEATHERS = ["clear", "snow"] satisfies readonly Weather[];

function sceneLabel(scene: SceneMood): string {
  return `${scene.dayPart} / ${scene.weather}`;
}

function SceneCell({
  scene,
  fallback,
}: {
  scene: SceneMood;
  fallback: boolean;
}) {
  const cue = wernerForScene(scene, { isFallback: fallback });
  const hasGap = POSE_GAPS.some((gap) => gap.sceneKey === cue.sceneKey);

  return (
    <div className="flex min-h-[210px] flex-col items-center justify-end gap-2 rounded-hog border-edge border-rule bg-ice-0 p-5 dark:bg-charcoal-2">
      <div className="flex flex-1 items-center justify-center">
        <Werner scene={scene} size={72} label={`Werner, ${sceneLabel(scene)}`} />
      </div>
      <div className="font-mono text-xs uppercase tracking-wider text-ink-soft dark:text-starlight">
        {sceneLabel(scene)}
      </div>
      <div className="font-mono text-[10px] text-ink-mute dark:text-moonlight">
        {cue.artPresence} / {cue.mood}
        {hasGap ? " / pose gap" : ""}
      </div>
      <p className="text-center font-serif text-[11px] leading-snug text-shadow-1 dark:text-moonlight">
        {cue.reason}
      </p>
      <p className="text-center font-serif text-[11px] leading-snug text-shadow-1 dark:text-moonlight">
        {cue.companionCopy}
      </p>
    </div>
  );
}

export const SceneMap: Story = {
  render: () => (
    <div className="min-h-screen bg-ice-2 p-8 dark:bg-space-2">
      <h1 className="mb-1 font-serif text-xl text-ink dark:text-bright">
        Werner scene map
      </h1>
      <p className="mb-6 max-w-2xl font-serif text-sm leading-relaxed text-shadow-1 dark:text-moonlight">
        Every scene state resolves to one sanctioned Werner pose. Fallback keeps
        him companionable; it never turns missing live art into an alarm.
      </p>
      <div className="grid gap-6">
        {([false, true] as const).map((fallback) => (
          <section key={fallback ? "fallback" : "live"}>
            <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-shadow-1 dark:text-moonlight">
              {fallback ? "procedural fallback" : "live art"}
            </h2>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              {DAY_PARTS.flatMap((dayPart) =>
                WEATHERS.map((weather) => (
                  <SceneCell
                    key={`${dayPart}-${weather}-${fallback ? "fallback" : "live"}`}
                    scene={{ dayPart, weather }}
                    fallback={fallback}
                  />
                )),
              )}
            </div>
          </section>
        ))}
      </div>
    </div>
  ),
};

function MomentCell({
  from,
  to,
  label,
}: {
  from: SceneMood | null;
  to: SceneMood;
  label: string;
}) {
  const moment = momentForTransition(from, to);
  const cue = wernerForScene(to);

  return (
    <div className="flex min-h-[190px] flex-col items-center justify-end gap-2 rounded-hog border-edge border-rule bg-ice-0 p-5 dark:bg-charcoal-2">
      <div className="flex flex-1 items-center justify-center">
        <Werner mood={moment?.pose ?? cue.mood} size={72} label={label} />
      </div>
      <div className="font-mono text-xs uppercase tracking-wider text-ink-soft dark:text-starlight">
        {label}
      </div>
      <div className="font-mono text-[10px] text-ink-mute dark:text-moonlight">
        {moment ? `${moment.id} / ${moment.durationMs}ms` : "no moment"}
      </div>
      <p className="text-center font-serif text-[11px] leading-snug text-shadow-1 dark:text-moonlight">
        {moment?.copy ?? "The resting cue is enough for this transition."}
      </p>
    </div>
  );
}

export const Moments: Story = {
  render: () => {
    const day: SceneMood = { dayPart: "day", weather: "snow" };
    const night: SceneMood = { dayPart: "night", weather: "snow" };
    const dusk: SceneMood = { dayPart: "dusk", weather: "snow" };
    const fallback = fallbackBeat(night);

    return (
      <div className="min-h-screen bg-ice-2 p-8 dark:bg-space-2">
        <h1 className="mb-1 font-serif text-xl text-ink dark:text-bright">
          Werner moments
        </h1>
        <p className="mb-6 max-w-2xl font-serif text-sm leading-relaxed text-shadow-1 dark:text-moonlight">
          Moments are one-shot reactions to scene changes. Each has a frequency
          cap and a no-focus interruption budget.
        </p>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <MomentCell from={day} to={night} label="day to night" />
          <MomentCell from={night} to={day} label="night to day" />
          <MomentCell from={day} to={dusk} label="day to dusk" />
          <div className="flex min-h-[190px] flex-col items-center justify-end gap-2 rounded-hog border-edge border-rule bg-ice-0 p-5 dark:bg-charcoal-2">
            <div className="flex flex-1 items-center justify-center">
              <Werner mood={fallback.moment.pose} size={72} label="fallback companion" />
            </div>
            <div className="font-mono text-xs uppercase tracking-wider text-ink-soft dark:text-starlight">
              procedural fallback
            </div>
            <div className="font-mono text-[10px] text-ink-mute dark:text-moonlight">
              {fallback.id} / {fallback.moment.frequencyCap.window}
            </div>
            <p className="text-center font-serif text-[11px] leading-snug text-shadow-1 dark:text-moonlight">
              {fallback.copy}
            </p>
          </div>
        </div>
      </div>
    );
  },
};
