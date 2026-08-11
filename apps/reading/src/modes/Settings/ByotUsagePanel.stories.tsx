import { useLayoutEffect, useState } from "react";
import type { Decorator, Meta, StoryObj } from "@storybook/react";
import { json } from "../Reading/storyFetch";
import ByotUsagePanel from "./ByotUsagePanel";

const models = {
  models: [
    { id: "user-deepseek", provider_kind: "openai_compat", provider_catalog_id: "deepseek", model_id: "deepseek-chat", display_name: "DeepSeek research", base_url: "https://api.deepseek.com", enabled: true, key_present: true, registered: true },
    { id: "user-kimi", provider_kind: "openai_compat", provider_catalog_id: "kimi", model_id: "kimi-k2", display_name: "Kimi long context", base_url: "https://api.moonshot.cn", enabled: true, key_present: true, registered: true },
  ],
  count: 2,
  stale_registered: [],
  source: "storybook",
};

function handleFetch(url: string, init?: RequestInit): Response {
  if (url.endsWith("/settings/models/user")) return json(models);
  if (url.endsWith("/settings/usage")) {
    return json({ keys: [
      { api_key_id: "user-deepseek", used_cents: 1842, limit_cents: 5000, remaining_cents: 3158 },
      { api_key_id: "user-kimi", used_cents: 625, limit_cents: null, remaining_cents: null },
    ], count: 2 });
  }
  if (url.includes("/settings/balance/user-deepseek")) {
    return json({ api_key_id: "user-deepseek", catalog_id: "deepseek", kind: "balance_native", balance_usd: 37.21, granted_usd: 50, spend_usd: null, budget_usd: null, utilization: null, window_label: null, resets_at: null, note: null });
  }
  if (url.includes("/settings/balance/user-kimi")) {
    return json({ api_key_id: "user-kimi", catalog_id: "kimi", kind: "unavailable", balance_usd: null, granted_usd: null, spend_usd: null, budget_usd: null, utilization: null, window_label: null, resets_at: null, note: "provider unavailable" });
  }
  if (url.includes("/settings/usage/") && url.endsWith("/limit") && init?.method === "POST") {
    return json({ api_key_id: "user-deepseek", used_cents: 1842, limit_cents: 5000, remaining_cents: 3158 });
  }
  return json({ detail: "not found" }, 404);
}

const decorator: Decorator = (Story) => {
  function FetchReadyStory() {
    const [ready, setReady] = useState(false);
    useLayoutEffect(() => {
      const original = window.fetch;
      window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        return Promise.resolve(handleFetch(url, init));
      }) as typeof window.fetch;
      setReady(true);
      return () => { window.fetch = original; };
    }, []);
    return ready ? <Story /> : null;
  }
  return <FetchReadyStory />;
};

const meta = {
  title: "Settings/BYOT usage and balances",
  component: ByotUsagePanel,
  decorators: [decorator],
  parameters: { layout: "padded" },
} satisfies Meta<typeof ByotUsagePanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const MixedAuthorityStates: Story = {};

export const Narrow: Story = {
  parameters: { viewport: { defaultViewport: "mobile1" } },
};
