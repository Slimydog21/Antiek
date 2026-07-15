import type { Meta, StoryObj } from "@storybook/react";
import { expect, waitFor } from "@storybook/test";

import Home from "./Home";

/**
 * Home (SPR-12 M1) — the unified branded front door.
 *
 * One branded statement of what Antiek is, four equal doors (one click into
 * each surface), biographies featured with an honest "still on its way"
 * label for the unbuilt SPR-11 guided flow. The global preview wraps every
 * story in a router, so navigation in the cards is harmless here.
 *
 * Visual baseline coverage: the home in light + dark (the top-left Werner
 * mark renders with the M4 alpha-cut pose, so there is no white box behind
 * it in the hero either).
 */
const meta = {
  title: "Home / Alpine knowledge campus (SPR-39)",
  component: Home,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof Home>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div className="h-screen w-screen">
      <Home />
    </div>
  ),
  play: async ({ canvasElement }) => {
    await waitFor(() => {
      expect(
        canvasElement.querySelector('[data-campus-image-ready="true"]'),
      ).toBeTruthy();
    });
    // The campus cards use backdrop-filter over a decoded image. Give Chromium
    // one compositor turn after load so visual baselines never capture the
    // pre-blur frame.
    await new Promise((resolve) => window.setTimeout(resolve, 300));
  },
};

export const ImageUnavailable: Story = {
  ...Default,
  play: async ({ canvasElement }) => {
    const image = canvasElement.querySelector<HTMLImageElement>(
      '[data-campus-map] img',
    );
    expect(image).toBeTruthy();
    image!.dispatchEvent(new Event("error"));
    await waitFor(() => {
      expect(canvasElement.querySelector('[data-campus-map] img')).toBeNull();
      expect(
        canvasElement.querySelectorAll(
          '[data-campus-map] button[data-workflow]',
        ),
      ).toHaveLength(4);
    });
  },
};

export const KeyboardFocus: Story = {
  ...Default,
  play: async ({ canvasElement }) => {
    await waitFor(() => {
      expect(
        canvasElement.querySelector('[data-campus-image-ready="true"]'),
      ).toBeTruthy();
    });
    const firstDoor = canvasElement.querySelector<HTMLButtonElement>(
      '[data-campus-map] button[data-workflow="research"]',
    );
    expect(firstDoor).toBeTruthy();
    firstDoor!.focus();
    await waitFor(() => expect(document.activeElement).toBe(firstDoor));
    await new Promise((resolve) => window.setTimeout(resolve, 300));
  },
};
