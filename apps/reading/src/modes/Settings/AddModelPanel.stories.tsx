import type { Meta, StoryObj } from "@storybook/react";

import AddModelPanel from "./AddModelPanel";

const meta = {
  title: "Settings / Bring your own model",
  component: AddModelPanel,
  parameters: {
    layout: "centered",
  },
  loaders: [
    async () => {
      window.fetch = async () =>
        new Response(
          JSON.stringify({
            models: [],
            count: 0,
            stale_registered: [],
            source: "Storybook fixture",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      return {};
    },
  ],
  decorators: [
    (Story) => (
      <div className="w-[min(42rem,calc(100vw-2rem))]">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof AddModelPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ProviderAndVariantPicker: Story = {};
