import type { Meta, StoryObj } from "@storybook/react";

import InvestigationsIndex from "./index";

/**
 * Investigations index page — lists past + in-flight investigations
 * with status filter chips, total cost, per-row workstation +
 * replay deep-links, and a "start new investigation" form.
 *
 * In Storybook (no backend) the listing renders empty and the
 * start-form is fully editable. Submitting the form fails the fetch
 * silently and surfaces the error text — useful for visually
 * verifying the error path.
 */
const meta = {
  title: "Workstation / InvestigationsIndex",
  component: InvestigationsIndex,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof InvestigationsIndex>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
