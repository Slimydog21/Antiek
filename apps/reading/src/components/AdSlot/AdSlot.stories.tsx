import type { Meta, StoryObj } from "@storybook/react";

import AdSlot, { type AdItem } from "./AdSlot";

const meta = {
  title: "Ad / AdSlot",
  component: AdSlot,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof AdSlot>;

export default meta;
type Story = StoryObj<typeof meta>;

const sampleAd: AdItem = {
  campaign_id: "cam-1234",
  advertiser_name: "Vertical SaaS Inc.",
  sector: "developer-tools",
  intent: "trial-signup",
  creative_headline: "Ship faster with a stack you didn't fight to assemble.",
  creative_url: "https://example.com/?ref=antiek",
};

export const PageBorder: Story = {
  args: {
    ad: sampleAd,
    pattern: "page-border",
  },
};

export const InlineSponsor: Story = {
  args: {
    ad: sampleAd,
    pattern: "inline-sponsor",
  },
};

export const Suppressed: Story = {
  args: {
    ad: sampleAd,
    pattern: "page-border",
    shouldSuppress: true,
    voiceContext: "synthesis-heavy paragraph",
  },
};

export const NoAd: Story = {
  args: {
    ad: null,
  },
};
