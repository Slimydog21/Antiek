import type { Meta, StoryObj } from "@storybook/react";

import Biography from "./index";

/**
 * Biography template landing (SPR-11).
 *
 * Storybook renders the real start page for the composed biography template:
 * a person name provisions Research first, then the Write + Speak composition
 * through the live app API. The submission path is covered with module mocks in
 * Biography.test.tsx; this story is the browser smoke target for the landing.
 */
const meta = {
  title: "Workstation / Biography",
  component: Biography,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof Biography>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Start: Story = {};
