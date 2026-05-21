import type { Meta, StoryObj } from "@storybook/react";

import type { Event } from "../generated/types";
import NotesFeed from "./NotesFeed";

/**
 * NotesFeed renders note.emerged events with confidence badges +
 * attribution chips. Master-spec §1 recursive-note-taking primary
 * surface (Sprint 5 day 1-2 ship; Sprint 17 included for design-
 * system documentation).
 */
const meta = {
  title: "Loop 2 / NotesFeed",
  component: NotesFeed,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof NotesFeed>;

export default meta;
type Story = StoryObj<typeof meta>;

function noteEvent(
  id: string,
  text: string,
  confidence: "high" | "moderate" | "low" | "unknown",
): Event {
  return {
    event_id: id,
    investigation_id: "inv-storybook-demo",
    document_id: "doc-quantum-2026",
    action_type: "note.emerged",
    emitted_at: new Date().toISOString(),
    role: "note_taker",
    payload: {
      action_type: "note.emerged",
      note_id: id,
      note_text: text,
      confidence,
      source_event_ids: ["evt-1", "evt-2"],
    } as never,
  } as Event;
}

export const ThreeNotes: Story = {
  args: {
    events: [
      noteEvent(
        "n-1",
        "Neutral-atom platforms now claim error rates below the surface-code threshold at intermediate scale, but the published values cluster suspiciously close to the threshold itself. The pattern suggests selection on which experiments to report rather than a settled engineering result.",
        "moderate",
      ),
      noteEvent(
        "n-2",
        "The Lukin group's results use a different gate-set decomposition than the Vuletic preprint; comparing the two error rates head-to-head requires re-normalizing for circuit depth.",
        "high",
      ),
      noteEvent(
        "n-3",
        "Decoherence times in trapped-ion systems remain an order of magnitude better than neutral atom platforms, but gate speeds are correspondingly slower; the relevant figure of merit is operations-per-coherence-time.",
        "low",
      ),
    ],
  },
};

export const Empty: Story = {
  args: { events: [] },
};
