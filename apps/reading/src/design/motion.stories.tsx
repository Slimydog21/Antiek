import type { Meta, StoryObj } from "@storybook/react";

import LemonButton from "../components/lemon/LemonButton";
import { cardLift } from "./motion";

/**
 * Stories — the inspection surface for U-05 M1/M5 base interactions.
 * Hover and press the buttons (the lift + offset-shadow snap) and the
 * cards (the gentle group-hover lift); confirm the same press feels the
 * same everywhere. Toggle the OS reduce-motion setting to see motion.css
 * collapse every transition to instant while the end states stay intact.
 */

const meta = {
  title: "Motion / Base interactions",
  parameters: { layout: "padded" },
} satisfies Meta;

export default meta;
type Story = StoryObj;

/** Press + hover-lift across the fill variants (the shared `press`). */
export const PressAndLift: Story = {
  render: () => (
    <div className="flex flex-wrap gap-4 p-8">
      <LemonButton variant="primary">Primary</LemonButton>
      <LemonButton variant="secondary">Secondary</LemonButton>
      <LemonButton variant="danger">Danger</LemonButton>
      <LemonButton variant="tertiary">Tertiary (bg shift)</LemonButton>
    </div>
  ),
};

/** Card-lift — the gentler group-hover nudge for a grid of cards. */
export const CardLift: Story = {
  render: () => (
    <div className="grid grid-cols-3 gap-5 p-8">
      {["One", "Two", "Three"].map((label) => (
        <div key={label} className="group cursor-pointer">
          <div
            className={`flex h-28 items-center justify-center rounded-hog border-edge border-sun bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright shadow-z1 dark:shadow-z1-night ${cardLift}`}
          >
            {label}
          </div>
        </div>
      ))}
    </div>
  ),
};
