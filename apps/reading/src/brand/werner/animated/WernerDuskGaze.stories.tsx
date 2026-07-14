import type { Meta, StoryObj } from "@storybook/react";

import WernerDuskGaze from "./WernerDuskGaze";

const meta = {
  title: "Brand / Werner / Dusk gaze (SPR-29)",
  component: WernerDuskGaze,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof WernerDuskGaze>;

export default meta;
type Story = StoryObj<typeof meta>;

export const FidelityPlate: Story = {
  render: () => (
    <main className="min-h-screen bg-space-2 p-8 text-bright">
      <section className="mx-auto max-w-5xl rounded-hog-lg border border-sun bg-charcoal-2 p-8 shadow-z2">
        <p className="font-mono text-xs uppercase tracking-widest text-starlight">SPR-29 · one mascot · one transition</p>
        <h1 className="mt-3 font-serif text-3xl">Werner notices the fading light.</h1>
        <p className="mt-3 max-w-2xl font-serif text-lg leading-8 text-bright">
          A committed scene transition may borrow this private pose once. It creates no fifth mood, clock, control, or replay.
        </p>
        <div className="mt-8 grid gap-5 md:grid-cols-3">
          <PoseCell label="Native station · 64 px" size={64} className="bg-ice-0 text-ink" />
          <PoseCell label="Dusk contrast · 160 px" size={160} className="bg-charcoal-1 text-bright" />
          <PoseCell label="Night contrast · 160 px" size={160} className="bg-space-1 text-bright" />
        </div>
      </section>
    </main>
  ),
};

function PoseCell({ label, size, className }: { label: string; size: number; className: string }) {
  return (
    <figure className={`flex min-h-64 flex-col items-center justify-end rounded-hog border border-rule p-5 ${className}`}>
      <WernerDuskGaze size={size} reduced />
      <figcaption className="mt-4 font-mono text-xs">{label}</figcaption>
    </figure>
  );
}
