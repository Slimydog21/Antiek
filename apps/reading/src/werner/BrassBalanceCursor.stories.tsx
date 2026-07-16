import type { Meta, StoryObj } from "@storybook/react";

import { BrassBalanceCursor } from "./BrassBalanceCursor";

const meta = {
  title: "Werner / Station instruments / Brass balance",
  component: BrassBalanceCursor,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof BrassBalanceCursor>;

export default meta;
type Story = StoryObj<typeof meta>;

export const CostPlanning: Story = {
  render: () => (
    <main className="min-h-screen bg-card-soft p-10 text-ink dark:text-bright">
      <div className="mx-auto grid max-w-5xl gap-7 md:grid-cols-[0.72fr_1.28fr]">
        <aside className="rounded-hog-lg border-edge border-rule bg-card p-6 shadow-z1">
          <p className="font-mono text-xs uppercase tracking-widest text-shadow-1">
            Cost plan
          </p>
          <ol className="mt-6 space-y-4 font-serif">
            <li>01 · Model allocation</li>
            <li>02 · Token budget</li>
            <li>03 · Provider weights</li>
          </ol>
        </aside>
        <article className="rounded-hog-lg border-edge border-rule bg-card p-9 shadow-z2">
          <p className="mb-4 font-mono text-xs uppercase tracking-widest text-shadow-1">
            Pricing · OpenRouter-style calculator
          </p>
          <h1 className="font-serif text-3xl leading-tight">
            Every cost is a trade-off the operator can weigh.
          </h1>
          <p className="mt-6 max-w-2xl font-serif text-lg leading-8">
            Move the brass balance through this ordinary, selectable HTML.
            Werner remains at his station; the pointer changes jobs when the
            workstation navigates to /pricing.
          </p>
          <hr className="my-8 border-rule" />
          <p className="font-serif text-lg leading-8">
            The scale settles when the pointer rests. Evidence stays evidence;
            the brass illustration supplies an atmosphere, never pricing data or
            interaction authority.
          </p>
        </article>
      </div>
      <BrassBalanceCursor />
    </main>
  ),
};

export const ReducedMotion: Story = {
  args: { disabled: true },
  render: (args) => (
    <main className="min-h-screen bg-card p-10 font-serif text-ink dark:text-bright">
      <p className="max-w-xl text-lg leading-8">
        Reduced motion removes the custom balance and preserves the native
        cursor. Pricing content and controls remain unchanged.
      </p>
      <BrassBalanceCursor {...args} />
    </main>
  ),
};
