import { useLayoutEffect, useState } from "react";
import type { Decorator, Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";

import TalkToBook from "./TalkToBook";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function handleFetch(url: string): Response {
  if (url.endsWith("/settings/models/user")) {
    return json({
      models: [{
        id: "user-deepseek",
        provider_kind: "openai_compat",
        model_id: "deepseek-chat",
        display_name: "DeepSeek V4 Flash",
        base_url: "https://api.deepseek.com",
        enabled: true,
        key_present: true,
        registered: true,
        route_eligible: true,
      }],
      count: 1,
      stale_registered: [],
      source: "storybook",
    });
  }
  if (url.endsWith("/books/story-book/ask")) {
    return json({
      answer_id: "story-answer",
      capture_status: "captured",
      answer: "The author distinguishes measured uncertainty from ambiguity in chapter four.",
      citations: [{
        chunk_id: "story-chunk",
        document_id: "story-book",
        page_index: 41,
        page_resolved: true,
        snippet: "Uncertainty can be measured; ambiguity changes the frame of the question.",
      }],
      grounded: true,
      context_chunk_count: 1,
      model_receipt: {
        authority: "owner_byot",
        requested_provider_id: "user-deepseek",
        requested_model_id: "deepseek-chat",
        actual_provider_id: "user-deepseek",
        actual_model_id: "deepseek-chat",
        authority_digest: "story-only-digest",
      },
    });
  }
  return json({ detail: "not found" }, 404);
}

const fetchDecorator: Decorator = (Story) => {
  function Ready() {
    const [ready, setReady] = useState(false);
    useLayoutEffect(() => {
      const original = window.fetch;
      window.fetch = ((input: RequestInfo | URL) => {
        const url = typeof input === "string"
          ? input
          : input instanceof URL ? input.toString() : input.url;
        return Promise.resolve(handleFetch(url));
      }) as typeof window.fetch;
      setReady(true);
      return () => { window.fetch = original; };
    }, []);
    return ready ? <Story /> : null;
  }
  return <Ready />;
};

const meta = {
  title: "Read/Talk to book",
  component: TalkToBook,
  decorators: [fetchDecorator],
  parameters: { layout: "fullscreen" },
  args: {
    documentId: "story-book",
    title: "The Shape of Uncertainty",
    onJumpToPage: () => undefined,
  },
} satisfies Meta<typeof TalkToBook>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ModelChoice: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole("button", { name: "Talk to this book" }));
    const chooser = await canvas.findByRole("combobox", { name: "Model for this answer" });
    await expect(chooser).toBeVisible();
    await userEvent.click(within(chooser).getByRole("button"));
    await userEvent.click(await canvas.findByRole("option", { name: /DeepSeek V4 Flash/ }));
    await expect(await canvas.findByText(/Requested: DeepSeek V4 Flash/)).toBeVisible();
    await userEvent.type(canvas.getByRole("textbox", { name: "Question for this book" }), "How does the author define uncertainty?");
    await userEvent.click(canvas.getByRole("button", { name: "Ask" }));
    await expect(await canvas.findByText(/Used user-deepseek · deepseek-chat/)).toBeVisible();
  },
};

export const Narrow: Story = {
  parameters: { viewport: { defaultViewport: "mobile1" } },
  play: ModelChoice.play,
};
