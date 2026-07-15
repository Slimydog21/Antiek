import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, waitFor, within } from "@storybook/test";

import FjordSkipHost from "./FjordSkipHost";

const meta = {
  title: "Brainstorm / Fjord Skip",
  component: FjordSkipHost,
  tags: ["a11y-audit"],
  parameters: {
    layout: "centered",
    lostpixel: {
      breakpoints: [375, 768, 1024, 1280],
      waitBeforeScreenshot: 350,
    },
  },
  decorators: [
    (Story) => (
      <div className="w-[min(960px,calc(100vw-32px))] bg-ice-1 p-4 dark:bg-space-2">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FjordSkipHost>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Offer: Story = {};

export const Playing: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(
      canvas.getByRole("button", { name: "Play Fjord Skip" }),
    );
    await waitFor(() => {
      expect(
        canvasElement.querySelector('[data-backdrop-ready="true"]'),
      ).toBeTruthy();
    });
  },
};
