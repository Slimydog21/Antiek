import type { Meta, StoryObj } from "@storybook/react";

import KeySheet from "./KeySheet";

/**
 * KeySheet — the keymap rendered from keymap.ts (`?` or prefix+?). One story
 * per theme and width: day and night, at 1280 px and at 390 px (a phone).
 * The sheet is a LemonModal fixed to the viewport, so the width is set with
 * the viewport addon (two named viewports below), the repo's pattern for
 * width stories (see AdBorder.stories.tsx).
 */
const VIEWPORTS = {
  desk1280: { name: "Desk 1280", styles: { width: "1280px", height: "800px" }, type: "desktop" },
  phone390: { name: "Phone 390", styles: { width: "390px", height: "844px" }, type: "mobile" },
};

const meta = {
  title: "Hotkeys/KeySheet",
  component: KeySheet,
  args: { onClose: () => {}, platform: "mac" },
  parameters: { viewport: { viewports: VIEWPORTS } },
} satisfies Meta<typeof KeySheet>;
export default meta;

type Story = StoryObj<typeof meta>;

const wide = { viewport: { viewports: VIEWPORTS, defaultViewport: "desk1280" } };
const phone = { viewport: { viewports: VIEWPORTS, defaultViewport: "phone390" } };

export const DayWide: Story = {
  parameters: wide,
  globals: { theme: "light", viewport: { value: "desk1280" } },
};

export const NightWide: Story = {
  parameters: wide,
  globals: { theme: "dark", viewport: { value: "desk1280" } },
};

export const DayPhone: Story = {
  parameters: phone,
  globals: { theme: "light", viewport: { value: "phone390" } },
};

export const NightPhone: Story = {
  parameters: phone,
  globals: { theme: "dark", viewport: { value: "phone390" } },
};

/** Windows/Linux keycaps (Ctrl, Alt) and no ⌘B row, day, 1280. */
export const DayWideOtherPlatform: Story = {
  args: { platform: "other" },
  parameters: wide,
  globals: { theme: "light", viewport: { value: "desk1280" } },
};
