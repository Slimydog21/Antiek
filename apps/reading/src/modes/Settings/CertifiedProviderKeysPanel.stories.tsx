import type { Meta, StoryObj } from "@storybook/react";

import CertifiedProviderKeysPanel from "./CertifiedProviderKeysPanel";

const meta = {
  title: "Settings / Certified dispatch keys",
  component: CertifiedProviderKeysPanel,
  parameters: { layout: "centered" },
  loaders: [async () => {
    window.fetch = async (input, init) => {
      if (init?.method === "PUT") {
        return Response.json({
          provider_handle: String(input).split("/").pop(),
          key_present: true,
          registered_providers: [String(input).split("/").pop()],
          source: "encrypted_byok_store",
        }, { status: 201 });
      }
      return Response.json({
        providers: [
          { provider_handle: "anthropic", key_present: false },
          { provider_handle: "deepseek", key_present: true },
          { provider_handle: "hermes", key_present: false },
          { provider_handle: "openrouter", key_present: false },
          { provider_handle: "xiaomi", key_present: true },
          { provider_handle: "zai", key_present: true },
        ],
        byot_only: false,
      });
    };
    return {};
  }],
  decorators: [(Story) => <div className="w-[min(44rem,calc(100vw-2rem))]"><Story /></div>],
} satisfies Meta<typeof CertifiedProviderKeysPanel>;

export default meta;
type Story = StoryObj<typeof meta>;
export const MixedKeyState: Story = {};
