import type { Meta, StoryObj } from "@storybook/react";

import SuggestedThemes from "./SuggestedThemes";

/**
 * SPR-11 M6/M7 — Storybook stories for the auto-suggested-themes stub.
 *
 * The Stub story is the only one that ships at SPR-11 closeout —
 * the feature flag is off, so the rendered component is the
 * empty-state copy + unlock-criteria pointer.
 *
 * The FlagOnEmpty + FlagOnWithSuggestions stories below would be
 * the post-unlock-criteria stories; we keep them as commented
 * scaffolding for the future-engineer flipping the flag. They MUST
 * NOT be exported until the flag actually flips, otherwise the
 * Storybook surface lies about the production state.
 */
const meta = {
  title: "Loop 2 / Theme Notebook / SuggestedThemes",
  component: SuggestedThemes,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof SuggestedThemes>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The stub at SPR-11 closeout. Empty section + unlock-criteria copy. */
export const Stub: Story = {
  args: {},
};
