import type { Meta, StoryObj } from "@storybook/react";

import ModePage from "./ModePage";
import LemonCard from "./LemonCard";

const meta = {
  title: "Lemon / ModePage",
  component: ModePage,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof ModePage>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div className="h-screen">
      <ModePage
        title="Billing summary"
        lede="Pay-as-you-go pricing. The page sits on the page ramp; cards keep the card tones so they lift off it."
      >
        <LemonCard elevation="z1" title="Free-tier usage">
          <p className="text-sm leading-relaxed">
            1,204,551 / 5,000,000 tokens · 24%
          </p>
        </LemonCard>
        <LemonCard elevation="z1" title="Totals">
          <p className="text-sm leading-relaxed">Total billable: $12.40</p>
        </LemonCard>
      </ModePage>
    </div>
  ),
};

export const WidthTiers: Story = {
  render: () => (
    <div className="grid grid-cols-2 gap-4 h-screen">
      {(["sm", "md", "lg", "xl"] as const).map((w) => (
        <div key={w} className="h-full border border-rule dark:border-charcoal-1">
          <ModePage width={w} title={`width="${w}"`} lede="One shell, four tiers.">
            <LemonCard elevation="z1">
              <p className="text-sm">Content column</p>
            </LemonCard>
          </ModePage>
        </div>
      ))}
    </div>
  ),
};

export const BespokeHeader: Story = {
  render: () => (
    <div className="h-screen">
      <ModePage
        width="sm"
        header={
          <header className="space-y-2">
            <p className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
              Custom header slot
            </p>
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Mascot art, tabs, meta lines — anything
            </h1>
          </header>
        }
      >
        <p className="text-sm text-ink dark:text-bright">
          The standard title/lede header is replaced verbatim.
        </p>
      </ModePage>
    </div>
  ),
};
