import type { CSSProperties, ComponentType } from "react";
import type { Meta, StoryObj } from "@storybook/react";

import {
  WernerCurious,
  WernerComposed,
  WernerDizzy,
  WernerHappy,
  WernerHit,
  WERNER_SEMANTIC_DURATION_MS,
} from ".";
import "./semantic-reactions.review.css";

type Reaction = "curious" | "happy" | "composed" | "dizzy" | "hit";
type ReactionComponent = ComponentType<{ size: number; reduced: boolean }>;

const REACTIONS: Record<Reaction, ReactionComponent> = {
  curious: WernerCurious,
  happy: WernerHappy,
  composed: WernerComposed,
  dizzy: WernerDizzy,
  hit: WernerHit,
};

const SEMANTIC_BEAT_MS: Record<Reaction, number> = {
  curious: 288,
  happy: 544,
  composed: 840,
  dizzy: 650,
  hit: 224,
};

const meta = {
  title: "Brand / Werner / Semantic motion proof",
  parameters: {
    layout: "fullscreen",
    chromatic: { disableSnapshot: false },
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const reactionOrder: Reaction[] = ["curious", "happy", "composed", "dizzy", "hit"];

export const ContactSheet: Story = {
  render: () => (
    <main className="min-h-screen bg-ice-2 p-4 text-ink dark:bg-space-2 dark:text-bright md:p-8">
      <h1 className="font-serif text-xl">Werner — semantic motion proof</h1>
      <p className="mb-6 mt-2 max-w-3xl font-serif text-sm italic text-ink-soft dark:text-starlight">
        Deterministic review frames. Each row freezes the same one-shot at its
        start, semantic evidence beat, settled end, and meaningful
        reduced-motion still.
      </p>
      <div className="grid grid-cols-[4.5rem_repeat(4,minmax(0,1fr))] gap-2 md:gap-3">
        <div aria-hidden="true" />
        {["Start · 0%", "Semantic beat", "Settle · 100%", "Reduced still"].map(
          (label) => (
            <div
              key={label}
              className="text-center font-mono text-[10px] uppercase tracking-wider text-ink-mute dark:text-moonlight"
            >
              {label}
            </div>
          ),
        )}
        {reactionOrder.map((reaction) => {
          const Component = REACTIONS[reaction];
          const frames = [
            { name: "start", elapsedMs: 0, reduced: false },
            {
              name: "semantic-beat",
              elapsedMs: SEMANTIC_BEAT_MS[reaction],
              reduced: false,
            },
            {
              name: "settle",
              elapsedMs: WERNER_SEMANTIC_DURATION_MS[reaction],
              reduced: false,
            },
            { name: "reduced", elapsedMs: 0, reduced: true },
          ] as const;

          return (
            <div key={reaction} className="contents">
              <div className="self-center font-mono text-xs font-semibold uppercase tracking-wider">
                {reaction}
              </div>
              {frames.map((frame) => {
                const style = {
                  "--werner-review-delay": `-${frame.elapsedMs}ms`,
                } as CSSProperties;
                return (
                  <div
                    key={frame.name}
                    className="werner-motion-proof__frame rounded-hog border-edge border-sun bg-ice-0 p-3 dark:bg-charcoal-2 md:p-5"
                    data-reaction={reaction}
                    data-review-frame={frame.name}
                    data-elapsed-ms={frame.elapsedMs}
                    style={style}
                  >
                    <Component size={88} reduced={frame.reduced} />
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </main>
  ),
};
