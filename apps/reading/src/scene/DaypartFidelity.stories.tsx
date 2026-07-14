import type { Meta, StoryObj } from "@storybook/react";

import { ProceduralSky } from "./layers/ProceduralSky";
import type { DayPart } from "./mood";

const meta = {
  title: "Scene / Daypart Fidelity",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const DAYPARTS = ["dawn", "day", "dusk", "night"] satisfies readonly DayPart[];

export const FourBoundedMoods: Story = {
  render: () => (
    <main className="min-h-screen bg-ice-2 p-6 md:p-8">
      <header className="mb-5 max-w-3xl">
        <p className="font-mono text-xs uppercase tracking-wider text-ink-mute">
          Mountain shell / authored fallback
        </p>
        <h1 className="mt-1 font-serif text-2xl text-ink">
          Four bounded moods
        </h1>
        <p className="mt-2 font-serif text-sm leading-relaxed text-shadow-1">
          OS theme owns the light or dark band. Local civil time selects only
          its brief dawn or dusk ambience; every plate remains deterministic
          offline.
        </p>
      </header>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {DAYPARTS.map((dayPart) => (
          <figure
            key={dayPart}
            className="overflow-hidden rounded-hog border-edge border-rule bg-ice-0"
          >
            <div className="relative h-48 md:h-64">
              <ProceduralSky mood={{ dayPart, weather: "snow" }} />
            </div>
            <figcaption className="flex items-baseline justify-between px-4 py-3">
              <span className="font-serif text-base capitalize text-ink">
                {dayPart}
              </span>
              <span className="font-mono text-[10px] uppercase tracking-wider text-ink-mute">
                {dayPart === "dawn" || dayPart === "day"
                  ? "OS light"
                  : "OS dark"}
              </span>
            </figcaption>
          </figure>
        ))}
      </div>
    </main>
  ),
};
