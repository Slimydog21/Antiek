import type { Meta, StoryObj } from "@storybook/react";

import {
  WernerCaughtAFish,
  WernerSleeping,
  WernerWaking,
  WernerThinking,
  WernerTobogganSpinner,
  WernerWaddle,
} from ".";
import Werner, { type WernerMood } from "../../Werner";
import {
  WernerCurious,
  WernerDizzy,
  WernerHappy,
  WernerHit,
} from "../reactions";

const meta = {
  title: "Brand / Werner / Animations",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const Cell = ({
  label,
  pose,
  hint,
}: {
  label: string;
  pose: React.ReactNode;
  hint: string;
}) => (
  <div className="flex flex-col items-center justify-end gap-2 bg-ice-0 dark:bg-charcoal-2 border-edge border-sun rounded-hog p-6 min-h-[180px]">
    <div className="flex-1 flex items-center justify-center">{pose}</div>
    <div className="text-xs font-mono uppercase tracking-wider text-ink-soft dark:text-starlight">
      {label}
    </div>
    <div className="text-[10px] font-mono text-ink-mute dark:text-moonlight text-center">
      {hint}
    </div>
  </div>
);

export const AllPoses: Story = {
  render: () => (
    <div className="p-8 bg-ice-2 dark:bg-space-2 min-h-screen">
      <h1 className="text-xl font-serif text-ink dark:text-bright mb-2">
        Werner — animated poses
      </h1>
      <p className="text-sm font-serif italic text-ink-soft dark:text-starlight mb-6">
        Brand spec § 10. Every animation honours
        <code className="font-mono">prefers-reduced-motion: reduce</code> via
        the CSS guard.
      </p>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <Cell
          label="Tobogganing"
          hint="streaming-investigation banner · loading spinner"
          pose={<WernerTobogganSpinner size={64} />}
        />
        <Cell
          label="Thinking"
          hint="AISidecar 'thinking…' state"
          pose={<WernerThinking size={56} />}
        />
        <Cell
          label="Caught a fish"
          hint="investigation-complete toast · one-shot"
          pose={<WernerCaughtAFish size={72} />}
        />
        <Cell
          label="Sleeping"
          hint="idle screen · empty-state"
          pose={<WernerSleeping size={120} />}
        />
        <Cell
          label="Waddle"
          hint="route-navigation transition"
          pose={<WernerWaddle size={48} />}
        />
      </div>
    </div>
  ),
};

export const ThinkingFidelity: Story = {
  render: () => (
    <div className="p-8 bg-ice-2 dark:bg-space-2 min-h-screen">
      <h1 className="text-xl font-serif text-ink dark:text-bright mb-2">
        Werner — thinking fidelity
      </h1>
      <p className="text-sm font-serif italic text-ink-soft dark:text-starlight mb-6">
        One canonical thinking pose and one accessible status at each supported
        size; external aurora dots keep ongoing work readable at rail scale.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[24, 40, 64].map((size) => (
          <Cell
            key={size}
            label={`${size}px`}
            hint="AI working · canonical thinking mood"
            pose={
              <WernerThinking
                size={size}
                label={`Werner thinking at ${size} pixels`}
              />
            }
          />
        ))}
      </div>
    </div>
  ),
};

export const SleepingFidelity: Story = {
  render: () => (
    <div className="p-8 bg-ice-2 dark:bg-space-2 min-h-screen">
      <h1 className="text-xl font-serif text-ink dark:text-bright mb-2">
        Werner — authored sleeping fidelity
      </h1>
      <p className="text-sm font-serif italic text-ink-soft dark:text-starlight mb-6">
        Reduced-motion stills prove the complete authored sleeping illustration
        at each supported review size without timing-dependent capture.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[48, 96, 120].map((size) => (
          <Cell
            key={size}
            label={`${size}px`}
            hint="idle hold · authored private pose"
            pose={
              <WernerSleeping
                size={size}
                label={`Werner sleeping at ${size} pixels`}
                reduced
              />
            }
          />
        ))}
      </div>
    </div>
  ),
};

export const RestLifecycleFidelity: Story = {
  render: () => (
    <div className="p-8 bg-ice-2 dark:bg-space-2 min-h-screen">
      <h1 className="text-xl font-serif text-ink dark:text-bright mb-2">
        Werner — long-rest lifecycle plates
      </h1>
      <p className="text-sm font-serif italic text-ink-soft dark:text-starlight mb-6">
        Deterministic semantic plates: persistent authored sleep, one authored
        wake arrival, and the reduced-motion neutral floor.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Cell
          label="Sleeping"
          hint="persistent hold"
          pose={<WernerSleeping size={96} reduced />}
        />
        <Cell
          label="Waking"
          hint="exactly once per sleep"
          pose={<WernerWaking size={96} reduced />}
        />
        <Cell
          label="Reduced motion"
          hint="lifecycle disabled · neutral still"
          pose={
            <Werner
              mood="idle"
              size={96}
              label="Werner at rest"
              className="werner-motion-static"
            />
          }
        />
      </div>
    </div>
  ),
};

export const SemanticReactions: Story = {
  render: () => (
    <div className="p-8 bg-ice-2 dark:bg-space-2 min-h-screen">
      <h1 className="text-xl font-serif text-ink dark:text-bright mb-2">
        Werner — semantic reaction reel
      </h1>
      <p className="text-sm font-serif italic text-ink-soft dark:text-starlight mb-6">
        Four honest beats: inspect, verify, recover, rebound. Canonical Werner
        remains the identity; each prop explains the event.
      </p>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Cell
          label="Curious"
          hint="evidence-card head tilt · 1200ms"
          pose={<WernerCurious size={80} reduced={false} />}
        />
        <Cell
          label="Happy"
          hint="archival verification · 800ms"
          pose={<WernerHappy size={80} reduced={false} />}
        />
        <Cell
          label="Dizzy"
          hint="one paperclip orbit · 1300ms"
          pose={<WernerDizzy size={80} reduced={false} />}
        />
        <Cell
          label="Hit"
          hint="brass-tab rebound · 800ms"
          pose={<WernerHit size={80} reduced={false} />}
        />
      </div>
    </div>
  ),
};

/* U-02 — the canonical single-component moods at the three critical sizes.
   16 px tests favicon legibility. 28 px is the rail. 120 px proves
   expression. The same canonical raster mapping serves every size. */
const moods: WernerMood[] = ["idle", "thinking", "empty", "celebrate"];
const sizes = [16, 28, 120];

export const CanonicalMoods: Story = {
  render: () => (
    <div className="p-8 bg-ice-2 dark:bg-space-2 min-h-screen">
      <h1 className="text-xl font-serif text-ink dark:text-bright mb-2">
        Werner — canonical moods (U-02)
      </h1>
      <p className="text-sm font-serif italic text-ink-soft dark:text-starlight mb-6">
        Single source. Rail mark must read "cute penguin" at 28 px. Restraint:
        only the four slots named in brand/README.md.
      </p>
      <div className="space-y-8">
        {moods.map((m) => (
          <div key={m}>
            <div className="uppercase text-[10px] tracking-[1.5px] text-shadow-1 dark:text-moonlight mb-2">
              {m}
            </div>
            <div className="flex items-end gap-8">
              {sizes.map((s) => (
                <div key={s} className="flex flex-col items-center gap-1.5">
                  <Werner mood={m} size={s} />
                  <div className="font-mono text-[10px] text-ink-mute">
                    {s}px
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  ),
};
