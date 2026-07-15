import type { Meta, StoryObj } from "@storybook/react";

import WernerNightWatch from "./WernerNightWatch";

const meta = {
  title: "Brand / Werner / Night watch (SPR-30)",
  component: WernerNightWatch,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof WernerNightWatch>;

export default meta;
type Story = StoryObj<typeof meta>;

export const FidelityPlate: Story = {
  render: () => (
    <main className="min-h-screen bg-space-2 p-8 text-bright">
      <section className="mx-auto max-w-5xl rounded-hog-lg border border-rule bg-charcoal-2 p-8 shadow-z2">
        <p className="font-mono text-xs uppercase tracking-widest text-starlight">SPR-30 · awake · settled · one transition</p>
        <h1 className="mt-3 font-serif text-3xl">The sky turns dark. Werner stays.</h1>
        <p className="mt-3 max-w-2xl font-serif text-lg leading-8 text-bright">
          Nightfall may borrow this private pose once. It is awake companionship—not sleep, a fifth mood, or a queued performance.
        </p>
        <div className="mt-8 grid gap-5 md:grid-cols-3">
          <PoseCell label="Native station · 64 px" size={64} className="bg-ice-0 text-ink" />
          <PoseCell label="Night watch · 160 px" size={160} className="bg-charcoal-1 text-bright" />
          <PoseCell label="Deep night · 160 px" size={160} className="bg-space-1 text-bright" />
        </div>
      </section>
    </main>
  ),
};

function PoseCell({ label, size, className }: { label: string; size: number; className: string }) {
  return (
    <figure className={`flex min-h-64 flex-col items-center justify-end rounded-hog border border-rule p-5 ${className}`}>
      <WernerNightWatch size={size} reduced />
      <figcaption className="mt-4 font-mono text-xs">{label}</figcaption>
    </figure>
  );
}
