import type { Meta, StoryObj } from "@storybook/react";

import HouseSlot from "./HouseSlot";

/**
 * The zero-buyer house state in isolation (Read SPR-05 M3). v1 ships with
 * no ad buyers, so this is the default fill — a useful "next read", never
 * blank or filler.
 */
const meta = {
  title: "Read / HouseSlot",
  component: HouseSlot,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof HouseSlot>;

export default meta;
type Story = StoryObj<typeof meta>;

export const PromotesAServableBook: Story = {
  args: {
    promo: { documentId: "doc-2", title: "On the Shortness of Life", author: "Seneca" },
  },
};

export const NeutralWhenNothingToPromote: Story = {
  args: { promo: null },
};
