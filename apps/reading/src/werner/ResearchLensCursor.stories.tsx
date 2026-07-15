import type { Meta, StoryObj } from "@storybook/react";

import { ResearchLensCursor } from "./ResearchLensCursor";

const meta = {
  title: "Werner / Station instruments / Research lens",
  component: ResearchLensCursor,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof ResearchLensCursor>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ObservatoryDesk: Story = {
  render: () => (
    <main className="min-h-screen bg-card-soft p-10 text-ink dark:text-bright">
      <div className="mx-auto grid max-w-5xl gap-6 md:grid-cols-[1.2fr_0.8fr]">
        <article className="rounded-hog-lg border-edge border-rule bg-card p-8 shadow-z2">
          <p className="mb-3 font-mono text-xs uppercase tracking-widest text-shadow-1">
            Evidence passage
          </p>
          <h1 className="font-serif text-3xl leading-tight">
            Move the lens across the argument.
          </h1>
          <p className="mt-5 max-w-2xl font-serif text-lg leading-8">
            The cursor changes jobs inside knowledge work: from a generic arrow
            into a quiet observatory instrument. The underlying passage remains
            ordinary, selectable HTML.
          </p>
        </article>
        <aside className="rounded-hog-lg border-edge border-rule bg-card p-6 shadow-z1">
          <p className="font-mono text-xs uppercase tracking-widest text-shadow-1">
            Provenance constellation
          </p>
          <ol className="mt-5 space-y-4 font-serif">
            <li>1 source passage</li>
            <li>3 linked claims</li>
            <li>2 unresolved questions</li>
          </ol>
        </aside>
      </div>
      <ResearchLensCursor />
    </main>
  ),
};

export const ReducedMotion: Story = {
  args: { disabled: true },
  render: (args) => (
    <main className="min-h-screen bg-card p-10 font-serif text-ink dark:text-bright">
      <p className="max-w-xl text-lg leading-8">
        Reduced motion disables the custom lens and leaves the native cursor
        untouched. The content and every control remain identical.
      </p>
      <ResearchLensCursor {...args} />
    </main>
  ),
};
