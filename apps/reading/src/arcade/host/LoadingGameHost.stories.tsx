import type { Meta, StoryObj } from "@storybook/react";

import { LoadingGameHost } from "./LoadingGameHost";

/**
 * Opt-in wait-state arcade host — never auto-plays over primary work.
 * Modes: plain-loader → offer → playing (pure waitHostLogic).
 */
const meta: Meta<typeof LoadingGameHost> = {
  title: "Arcade/LoadingGameHost",
  component: LoadingGameHost,
  parameters: {
    layout: "centered",
  },
  args: {
    waiting: true,
    ready: false,
    arcadeEnabled: true,
    offerAfterMs: 0,
    game: "zombies",
    primaryControlLabel: "Back to work",
  },
};

export default meta;
type Story = StoryObj<typeof LoadingGameHost>;

export const OfferZombies: Story = {
  name: "Offer · Paperclip Zombies",
};

export const OfferIceFishing: Story = {
  name: "Offer · Ice Fishing",
  args: { game: "ice-fishing" },
};

export const PlainLoaderFlagOff: Story = {
  name: "Plain loader · arcade flag off",
  args: { arcadeEnabled: false },
};

export const HiddenWhenReady: Story = {
  name: "Hidden when ready",
  args: { ready: true },
};
