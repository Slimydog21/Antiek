import type { Meta, StoryObj } from "@storybook/react";

import { UnsourcedClaimGuard } from "./index";

/**
 * FFX SPR-04 M6 (F-15): the Multimedia provenance guard on its real panel
 * (the storyboard section: bg-ice-1 / dark:bg-charcoal-2).
 *
 * Tailwind here is darkMode: "media", so the `dark:` classes apply only when
 * the browser reports prefers-color-scheme: dark. The Storybook toolbar cannot
 * set that; to see the night variant emulate it (Chrome DevTools → Rendering →
 * "Emulate CSS media feature prefers-color-scheme: dark"). Lost-pixel's
 * Chromium does not emulate it, so its shot of this story is the day variant.
 * The night contrast is pinned by Multimedia.darkFocus.test.tsx.
 */
const meta = {
  title: "Modes / Multimedia / UnsourcedClaimGuard",
  component: UnsourcedClaimGuard,
  parameters: { layout: "padded" },
  args: { claims: [], persisted: false },
  render: (args) => (
    <div className="max-w-xl rounded-md bg-ice-1 p-4 dark:bg-charcoal-2">
      <UnsourcedClaimGuard {...args} />
    </div>
  ),
} satisfies Meta<typeof UnsourcedClaimGuard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ExampleOnly: Story = {};

export const WithClaims: Story = {
  args: {
    persisted: true,
    claims: [
      "Solar deployment doubled every three years since 2010.",
      "Lithium refining is concentrated in two countries.",
    ],
  },
};

export const NightWithClaims: Story = {
  name: "Night · with claims (emulate prefers-color-scheme: dark)",
  parameters: { backgrounds: { default: "charcoal-2 (night card)" } },
  args: WithClaims.args,
};
