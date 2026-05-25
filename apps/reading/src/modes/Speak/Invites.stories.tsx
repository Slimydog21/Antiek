import type { Meta, StoryObj } from "@storybook/react";

import Invites, { type InviteRow } from "./Invites";

/**
 * Speak SPR-03 M2 — the invitation surface. Invitees are sources, not
 * accounts; the public ecosystem is gated on G7. Stories seed invites
 * directly (no backend).
 */
const meta = {
  title: "Workstation / Speak / Invites",
  component: Invites,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof Invites>;

export default meta;
type Story = StoryObj<typeof meta>;

const PRIVATE_INVITES: InviteRow[] = [
  {
    interviewId: "interview-aaa111",
    email: "uncle.fawzi@example.com",
    handle: null,
    status: "completed",
    link: "https://interview.antiek.ai/interview-aaa111?token=abc123",
    requiredScopes: ["record"],
  },
  {
    interviewId: "interview-bbb222",
    email: "aunt.mona@example.com",
    handle: null,
    status: "in_progress",
    link: "https://interview.antiek.ai/interview-bbb222?token=def456",
    requiredScopes: ["record"],
  },
  {
    interviewId: "interview-ccc333",
    email: "old.colleague@example.com",
    handle: null,
    status: "declined",
    link: "https://interview.antiek.ai/interview-ccc333?token=ghi789",
    requiredScopes: ["record"],
  },
];

export const PrivateProject: Story = {
  args: {
    projectTitle: "Dad's biography",
    publishIntent: "private_never_published",
    invites: PRIVATE_INVITES,
    onInvite: (email) =>
      // eslint-disable-next-line no-console
      console.log(`invite ${email}`),
  },
};

export const WillBePublic: Story = {
  args: {
    projectTitle: "A community history",
    publishIntent: "will_be_public",
    invites: [
      {
        interviewId: "interview-ddd444",
        email: "neighbor@example.com",
        handle: null,
        status: "invited",
        link: "https://interview.antiek.ai/interview-ddd444?token=jkl012",
        requiredScopes: ["record", "attribute", "publish"],
      },
    ],
    onInvite: (email) =>
      // eslint-disable-next-line no-console
      console.log(`invite ${email}`),
  },
};

export const Empty: Story = {
  args: {
    projectTitle: "New project",
    publishIntent: "private_never_published",
    invites: [],
  },
};
