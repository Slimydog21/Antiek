import type { Meta, StoryObj } from "@storybook/react";

import ByotUsagePanel from "./ByotUsagePanel";

const meta = {
  title: "Settings / Key usage ledger",
  component: ByotUsagePanel,
  parameters: { layout: "centered" },
  loaders: [async () => {
    window.fetch = async (input) => {
      const url = String(input);
      if (url.endsWith("/settings/usage")) {
        return Response.json({ keys: [
          { api_key_id: "user-deepseek-reasoner", used_cents: 1234, limit_cents: 5000, remaining_cents: 3766 },
          { api_key_id: "user-mimo-flash", used_cents: 87, limit_cents: null, remaining_cents: null },
          { api_key_id: "user-kimi-research", used_cents: 4200, limit_cents: 6000, remaining_cents: 1800 },
        ], count: 3 });
      }
      const id = decodeURIComponent(url.split("/").pop() ?? "");
      const fixtures: Record<string, object> = {
        "user-deepseek-reasoner": { api_key_id: id, catalog_id: "deepseek", kind: "balance_native", balance_usd: 8.75, note: "Provider-reported balance" },
        "user-mimo-flash": { api_key_id: id, catalog_id: "mimo", kind: "meter_only", note: "No native balance endpoint" },
        "user-kimi-research": { api_key_id: id, catalog_id: "kimi", kind: "unavailable", note: "Provider endpoint timed out" },
      };
      return Response.json(fixtures[id]);
    };
    return {};
  }],
  decorators: [(Story) => <div className="w-[min(48rem,calc(100vw-2rem))]"><Story /></div>],
} satisfies Meta<typeof ByotUsagePanel>;

export default meta;
type Story = StoryObj<typeof meta>;
export const MixedProviderSignals: Story = {};
