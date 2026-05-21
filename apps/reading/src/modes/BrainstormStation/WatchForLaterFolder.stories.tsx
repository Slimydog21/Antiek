import type { Meta, StoryObj } from "@storybook/react";

import type { ParkedQuestionEntry } from "../../lib/api";
import WatchForLaterFolder from "./WatchForLaterFolder";

/**
 * Watch-for-later folder in the Brainstorming Workstation
 * (Surface E, master-spec §4.5 — operator's stated preferred product
 * direction). Renders unsharpened question.identified events from
 * the substrate, ordered newest-first.
 *
 * The folder is the curiosity-capture primitive surface (§2.6) —
 * the place where rough ideas that are not sharpened yet help the
 * user extract their curiosity and encode it in technology.
 */
const meta = {
  title: "Surface E — Brainstorm / WatchForLaterFolder",
  component: WatchForLaterFolder,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof WatchForLaterFolder>;

export default meta;
type Story = StoryObj<typeof meta>;

function parked(
  id: string,
  text: string,
  minutesAgo: number,
): ParkedQuestionEntry {
  return {
    question_id: id,
    question_text: text,
    source_investigation_id: `inv-${id.slice(0, 6)}`,
    source_document_id: null,
    anchor_region_id: null,
    parked_at: new Date(Date.now() - minutesAgo * 60_000).toISOString(),
    parent_event_id: null,
  };
}

export const Loading: Story = {
  args: {
    questions: [],
    loading: true,
    error: null,
    selectedId: null,
    onSelect: () => {},
  },
};

export const Empty: Story = {
  args: {
    questions: [],
    loading: false,
    error: null,
    selectedId: null,
    onSelect: () => {},
  },
};

export const ThreeParked: Story = {
  args: {
    questions: [
      parked(
        "q-quantum-1",
        "How does QuEra's gate-set decomposition compare head-to-head with the Vuletic preprint when normalized for circuit depth?",
        12,
      ),
      parked(
        "q-defense-2",
        "What's the actual cost-per-target for low-orbit ASAT platforms vs the published numbers from Soviet-era ground-based systems?",
        90,
      ),
      parked(
        "q-history-3",
        "Did the 1944 Bretton Woods agreement design assume that the dollar would become the de-facto reserve currency, or did that emerge later from imbalances no one anticipated?",
        420,
      ),
    ],
    loading: false,
    error: null,
    selectedId: "q-defense-2",
    onSelect: () => {},
  },
};

export const ErrorState: Story = {
  args: {
    questions: [],
    loading: false,
    error: "GET /watch-for-later failed: HTTP 503",
    selectedId: null,
    onSelect: () => {},
  },
};
