import type { Meta, StoryObj } from "@storybook/react";

import InvestigationsIndex from "./index";

/**
 * Retired standalone investigations index — the preserved component
 * that used to list past + in-flight investigations with status
 * filters, total cost, per-row Research home + replay deep-links, and
 * a "start new investigation" form.
 *
 * In production, the old /investigations door redirects into the
 * canonical /my-research monitor. Storybook keeps this chrome around
 * as a regression target for the retired component and its error path.
 */
const meta = {
  title: "Research / InvestigationsIndex",
  component: InvestigationsIndex,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof InvestigationsIndex>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
