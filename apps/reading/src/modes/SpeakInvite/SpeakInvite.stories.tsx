import type { Meta, StoryObj } from "@storybook/react";

import SpeakInvite from "./index";

/**
 * Speak invitee landing (specs/speak/) — the friends-and-family page.
 *
 * Unauthenticated + token-gated: the URL token is the credential. With
 * no token in the Storybook MemoryRouter, the page shows its
 * invalid-link state (the honest failure mode for a bad/expired link).
 * The live flow — resolve → scoped consent → answer → done — is
 * exercised end-to-end in tests/test_speak_api.py.
 */
const meta = {
  title: "Workstation / Speak / Invitee Landing",
  component: SpeakInvite,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof SpeakInvite>;

export default meta;
type Story = StoryObj<typeof meta>;

export const InvalidLink: Story = {};
