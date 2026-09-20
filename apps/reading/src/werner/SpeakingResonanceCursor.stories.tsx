import type { Meta, StoryObj } from "@storybook/react";

import { SpeakingResonanceCursor } from "./SpeakingResonanceCursor";

const meta = {
  title: "Werner / Station instruments / Speaking resonance",
  component: SpeakingResonanceCursor,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof SpeakingResonanceCursor>;

export default meta;
type Story = StoryObj<typeof meta>;

export const AlpineRadioStudio: Story = {
  render: () => (
    <main className="min-h-screen bg-card-soft p-10 text-ink dark:text-bright">
      <div className="mx-auto grid max-w-5xl gap-7 md:grid-cols-[1.2fr_0.8fr]">
        <article className="rounded-hog-lg border-edge border-rule bg-card p-9 shadow-z2">
          <p className="mb-4 font-mono text-xs uppercase tracking-widest text-shadow-1">
            Oral history session · listening
          </p>
          <h1 className="font-serif text-3xl leading-tight">
            Let the story arrive in the speaker’s own rhythm.
          </h1>
          <p className="mt-6 max-w-2xl font-serif text-lg leading-8">
            Move the small resonance microphone through this ordinary HTML. It
            signals the job of the Speak surface without requesting a real
            microphone, reading a transcript, or moving Werner from home.
          </p>
        </article>
        <aside className="rounded-hog-lg border-edge border-rule bg-card p-6 shadow-z1">
          <p className="font-mono text-xs uppercase tracking-widest text-shadow-1">
            Listening posture
          </p>
          <ul className="mt-5 space-y-4 font-serif">
            <li>Hold the question lightly</li>
            <li>Keep the speaker’s cadence</li>
            <li>Mark uncertainty honestly</li>
          </ul>
        </aside>
      </div>
      <SpeakingResonanceCursor />
    </main>
  ),
};

export const ReducedMotion: Story = {
  args: { disabled: true },
  render: (args) => (
    <main className="min-h-screen bg-card p-10 font-serif text-ink dark:text-bright">
      <p className="max-w-xl text-lg leading-8">
        Reduced motion removes the resonance instrument and preserves the native
        cursor. No recording or content behavior changes.
      </p>
      <SpeakingResonanceCursor {...args} />
    </main>
  ),
};
