import { useLayoutEffect, useState } from "react";
import type { Decorator, Meta, StoryObj } from "@storybook/react";
import AddModelPanel from "./AddModelPanel";

const catalog = {
  providers: [
    {
      catalog_id: "openai",
      display: "OpenAI",
      provider_kind: "openai_compat",
      default_base_url: "https://api.openai.com",
      models: [
        {
          id: "gpt-5.6-sol",
          label: "GPT-5.6 Sol",
          snapshot: "openai-sol-story",
        },
        {
          id: "gpt-5.6-luna",
          label: "GPT-5.6 Luna",
          snapshot: "openai-luna-story",
        },
      ],
      pricing_source: "https://developers.openai.com/api/docs/models",
    },
    {
      catalog_id: "anthropic",
      display: "Anthropic",
      provider_kind: "anthropic",
      default_base_url: "https://api.anthropic.com",
      models: [
        {
          id: "claude-opus-5",
          label: "Claude Opus 5",
          snapshot: "anthropic-opus-story",
        },
      ],
      pricing_source: "https://platform.claude.com/docs/models",
    },
  ],
  count: 2,
};

const inventory = {
  models: [
    {
      id: "user-long-model",
      provider_kind: "openai_compat",
      provider_catalog_id: "openai",
      model_id:
        "provider/model-with-an-extremely-long-unbroken-identifier-for-narrow-layout",
      display_name: "Editorial research model",
      base_url: "https://api.openai.com",
      enabled: true,
      key_present: true,
      registered: true,
      route_eligible: true,
      pricing_status: "known",
      hard_ceiling_eligible: false,
      execution_status: "blocked_idempotency_unproven",
      rate_snapshot: "story-snapshot",
    },
  ],
  count: 1,
  stale_registered: [],
  source: "storybook",
};

const fetchDecorator: Decorator = (Story) => {
  function Ready() {
    const [ready, setReady] = useState(false);
    useLayoutEffect(() => {
      const original = window.fetch;
      window.fetch = ((input: RequestInfo | URL) => {
        const url =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.toString()
              : input.url;
        const body = url.endsWith("/settings/models/catalog")
          ? catalog
          : inventory;
        return Promise.resolve(
          new Response(JSON.stringify(body), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }) as typeof window.fetch;
      setReady(true);
      return () => {
        window.fetch = original;
      };
    }, []);
    return ready ? <Story /> : null;
  }
  return <Ready />;
};

const meta = {
  title: "Settings/Add model panel",
  component: AddModelPanel,
  decorators: [
    fetchDecorator,
    (Story) => (
      <main className="mx-auto max-w-3xl p-4">
        <Story />
      </main>
    ),
  ],
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof AddModelPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Desktop: Story = {};

export const Narrow390: Story = {
  parameters: { viewport: { defaultViewport: "mobile1" } },
};
