import type { Meta, StoryObj } from "@storybook/react";

import ErrorBanner from "./ErrorBanner";

const meta = {
  title: "Lemon / ErrorBanner",
  component: ErrorBanner,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof ErrorBanner>;

export default meta;
type Story = StoryObj<typeof meta>;

export const LoadFailure: Story = {
  render: () => (
    <div className="max-w-xl p-6">
      <ErrorBanner>Couldn&rsquo;t load investigations. Check your connection and retry.</ErrorBanner>
    </div>
  ),
};

export const QuietStatus: Story = {
  render: () => (
    <div className="max-w-xl p-6">
      <ErrorBanner role="status">
        Some rows were skipped because the source revoked access.
      </ErrorBanner>
    </div>
  ),
};
