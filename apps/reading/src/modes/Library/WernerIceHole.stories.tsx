import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, waitFor, within } from "@storybook/test";

import WernerIceHole from "./WernerIceHole";

const meta = {
  title: "Read / Werner ice hole",
  component: WernerIceHole,
  parameters: {
    layout: "centered",
    lostpixel: {
      breakpoints: [375, 768, 1024, 1280],
      waitBeforeScreenshot: 350,
    },
  },
  decorators: [
    (Story) => (
      <div className="w-[min(680px,calc(100vw-32px))] bg-ice-1 p-4 dark:bg-space-2">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof WernerIceHole>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Offer: Story = {};

export const Playing: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(
      canvas.getByRole("button", { name: "Play Ice Fishing" }),
    );
    await waitFor(() => {
      expect(
        canvasElement.querySelector('[data-backdrop-ready="true"]'),
      ).toBeTruthy();
    });
  },
};
