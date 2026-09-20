import type { Meta, StoryObj } from "@storybook/react";

import { WritingNibCursor } from "./WritingNibCursor";

const meta = {
  title: "Werner / Station instruments / Writing nib",
  component: WritingNibCursor,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof WritingNibCursor>;

export default meta;
type Story = StoryObj<typeof meta>;

export const AlpineScriptorium: Story = {
  render: () => (
    <main className="min-h-screen bg-card-soft p-10 text-ink dark:text-bright">
      <div className="mx-auto grid max-w-5xl gap-7 md:grid-cols-[0.72fr_1.28fr]">
        <aside className="rounded-hog-lg border-edge border-rule bg-card p-6 shadow-z1">
          <p className="font-mono text-xs uppercase tracking-widest text-shadow-1">
            Draft constellation
          </p>
          <ol className="mt-6 space-y-4 font-serif">
            <li>01 · Working claim</li>
            <li>02 · Source tension</li>
            <li>03 · Unresolved question</li>
          </ol>
        </aside>
        <article className="rounded-hog-lg border-edge border-rule bg-card p-9 shadow-z2">
          <p className="mb-4 font-mono text-xs uppercase tracking-widest text-shadow-1">
            Working page · unsaved thought
          </p>
          <h1 className="font-serif text-3xl leading-tight">
            A draft is an instrument for finding the thought.
          </h1>
          <p className="mt-6 max-w-2xl font-serif text-lg leading-8">
            Move the brass nib through this ordinary, selectable HTML. Werner
            remains at his alpine station; the pointer changes jobs when the
            workstation enters Write or Create.
          </p>
          <hr className="my-8 border-rule" />
          <p className="font-serif text-lg leading-8">
            Evidence stays evidence. The scriptorium illustration supplies an
            atmosphere, never document content or interaction authority.
          </p>
        </article>
      </div>
      <WritingNibCursor />
    </main>
  ),
};

export const ReducedMotion: Story = {
  args: { disabled: true },
  render: (args) => (
    <main className="min-h-screen bg-card p-10 font-serif text-ink dark:text-bright">
      <p className="max-w-xl text-lg leading-8">
        Reduced motion removes the custom nib and preserves the native cursor.
        Writing content and controls remain unchanged.
      </p>
      <WritingNibCursor {...args} />
    </main>
  ),
};
