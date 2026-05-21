import type { Meta, StoryObj } from "@storybook/react";

import type { Event } from "../generated/types";
import NotesPanel from "./NotesPanel";

/**
 * NotesPanel is the right-column chat feed in Loop 2 wrestling mode.
 * Composes the full trajectory as a chat-style feed with user bubbles
 * (ask + challenge), assistant claim-card groups, and muted system
 * rows. Master-spec §4.2 + §1 recursive note-taking surface.
 *
 * Sprint 17 included for design-system documentation. Note that the
 * Sprint 18-19 Wedge 2 notebook surface (master §4.2 upgrade) is the
 * higher-leverage ceiling on this baseline.
 */
const meta = {
  title: "Loop 2 / NotesPanel",
  component: NotesPanel,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof NotesPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

function userAsk(id: string, text: string): Event {
  return {
    event_id: id,
    investigation_id: "inv-storybook-demo",
    document_id: "doc-quantum-2026",
    action_type: "distillation.requested",
    emitted_at: new Date().toISOString(),
    role: "operator",
    payload: {
      action_type: "distillation.requested",
      prompt: text,
    } as never,
  } as Event;
}

export const ConnectingEmpty: Story = {
  args: {
    events: [],
    status: "connecting",
    reconnects: 0,
    investigationId: "inv-storybook-demo",
    documentId: "doc-quantum-2026",
  },
};

export const OpenWithUserMessage: Story = {
  args: {
    events: [
      userAsk(
        "evt-ask-1",
        "What's the published error rate for neutral-atom platforms at 100-qubit scale?",
      ),
    ],
    status: "open",
    reconnects: 0,
    investigationId: "inv-storybook-demo",
    documentId: "doc-quantum-2026",
  },
};

export const ClosedWithReconnects: Story = {
  args: {
    events: [],
    status: "closed",
    reconnects: 3,
    investigationId: "inv-storybook-demo",
    documentId: "doc-quantum-2026",
  },
};
