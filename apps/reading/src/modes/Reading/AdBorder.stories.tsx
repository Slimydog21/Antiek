import type { Meta, StoryObj } from "@storybook/react";

import AdBorder from "./AdBorder";

const meta = {
  title: "Read / AdBorder",
  component: AdBorder,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof AdBorder>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The v1 default: zero buyers → a useful house promotion, never blank. */
export const ZeroBuyerHouse: Story = {
  args: {
    slotId: "slot:doc-1:p0:top",
    position: "top",
    fill: {
      kind: "house",
      house: { documentId: "doc-2", title: "On the Shortness of Life", author: "Seneca" },
    },
  },
};

/** Zero buyers AND nothing to promote — a neutral, non-broken card. */
export const ZeroBuyerNeutral: Story = {
  args: {
    slotId: "slot:doc-1:p0:bottom",
    position: "bottom",
    fill: { kind: "house", house: null },
  },
};

/** A matched paid ad. Clearly labelled "Sponsored". */
export const PaidAd: Story = {
  args: {
    slotId: "slot:doc-1:p0:top",
    position: "top",
    fill: {
      kind: "ad",
      ad: {
        advertiserName: "A Relevant Advertiser",
        creativeUrl: "https://placehold.co/64",
        landingUrl: "https://example.com",
      },
    },
  },
};

/** In context: a reading column with rails above and below, showing that
 * the reading column is never narrowed (rails are top/bottom only). */
export const AroundReadingColumn: Story = {
  render: () => (
    <div className="max-w-2xl mx-auto flex flex-col gap-4">
      <AdBorder
        slotId="slot:doc-1:p3:top"
        position="top"
        fill={{ kind: "house", house: { documentId: "d2", title: "Meditations", author: "Marcus Aurelius" } }}
      />
      <p className="font-serif text-[15px] leading-[1.7] text-ink dark:text-bright">
        The reading column sits between the rails, full width, never narrowed.
        An ad rail above and below keeps the economics present without
        crowding the prose.
      </p>
      <AdBorder
        slotId="slot:doc-1:p3:bottom"
        position="bottom"
        fill={{ kind: "house", house: null }}
      />
    </div>
  ),
};
