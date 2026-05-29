import type { Meta, StoryObj } from "@storybook/react";

import ReadingColumn from "./ReadingColumn";

const SAMPLE = `# On the Shortness of Life

It is not that we have a short time to live, but that we waste a great deal of it. Life is long enough, and a sufficiently generous amount has been given to us for the highest achievements if it were all well invested.

But when it is wasted in heedless luxury and spent on no good activity, we are forced at last by death's final constraint to realize that it has passed away before we knew it was passing.

## The Verdict

So it is: we are not given a short life but we make it short, and we are not ill-supplied but wasteful of it.`;

const meta = {
  title: "Read / Reader / ReadingColumn",
  component: ReadingColumn,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof ReadingColumn>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A servable work: the column is tagged with data-akb-asset-id, so the
 *  shell-level SPR-07 sampler attributes in-frame seconds to it. */
export const Servable: Story = {
  args: { assetId: "doc-seneca", text: SAMPLE },
};

/** A gated preview: no asset id → the column renders the snippet UNTAGGED, so a
 *  preview is never attributed as a monetized asset (§9.0). */
export const GatedPreview: Story = {
  args: { assetId: null, text: "A short, gate-served snippet — metadata-tier only." },
};

export const EmptyBody: Story = {
  args: { assetId: "doc-empty", text: "" },
};
