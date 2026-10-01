import type { Meta, StoryObj } from "@storybook/react";
import { useLayoutEffect, type ReactNode } from "react";
import { AuthProvider } from "../../lib/auth";

import ChatInputArea from "./ChatInputArea";

/** Fixture-only auth/API boundary for this one composer story. */
function ChatStoryFixture({ children }: { children: ReactNode }) {
  useLayoutEffect(() => {
    const original = globalThis.fetch;
    const fixture: typeof fetch = async (input, init) => {
      const path = new URL(String(input), window.location.origin).pathname;
      if (path === "/auth/me")
        return Response.json({
          user_id: "story-fixture",
          email: null,
          auth_method: "antiek_session_cookie",
        });
      if (path === "/settings/models/user")
        return Response.json({
          models: [],
          count: 0,
          stale_registered: [],
          source: "story fixture",
        });
      if (path === "/settings/usage")
        return Response.json({ keys: [], count: 0 });
      if (path === "/investigations" && init?.method === "POST")
        return Response.json({
          investigation_id: "inv-story-fixture",
          status: "in_progress",
          start_event_id: "story-start",
        });
      return new Response(null, { status: 404 });
    };
    globalThis.fetch = fixture;
    return () => {
      if (globalThis.fetch === fixture) globalThis.fetch = original;
    };
  }, []);
  return <AuthProvider>{children}</AuthProvider>;
}

/**
 * ChatInputArea — the pinned-bottom composer in the ResearchWorkstation.
 * Submit posts an investigation.start_requested event and (by default)
 * navigates to /inv/<new id>. In Storybook the submit handler is wired
 * to `onSubmitted` to capture the action instead of doing real navigation.
 */
const meta = {
  title: "Loop 1 / ChatInputArea",
  component: ChatInputArea,
  parameters: { layout: "padded" },
  decorators: [
    (Story) => (
      <ChatStoryFixture>
        <Story />
      </ChatStoryFixture>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof ChatInputArea>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Empty: Story = {
  args: {
    placeholder: "What do you want to research?",
    autoFocus: true,
    onSubmitted: (id) => alert(`submitted, new id = ${id}`),
  },
};

export const ChildOfInvestigation: Story = {
  args: {
    parentInvestigationId: "inv-storybook-demo",
    spawnContext:
      "the gap between groups is a genuine difference in platform physics",
    placeholder: "Ask a follow-up…",
    onSubmitted: (id) => alert(`submitted, new id = ${id}`),
  },
};
