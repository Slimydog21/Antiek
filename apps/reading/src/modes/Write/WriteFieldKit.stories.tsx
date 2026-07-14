import type { Meta, StoryObj } from "@storybook/react";

import WriteFieldKit from "./WriteFieldKit";

const HITS = [
  {
    node_id: "story-insight-1",
    label: "Inference cost falls while verification cost remains stubborn",
    node_type: "insight",
    source_tier: 1,
    document_id: "story-doc-1",
    document_title: "Frontier model economics · field notes",
    score: 0.94,
  },
  {
    node_id: "story-question-2",
    label: "Which coordination costs survive cheaper inference?",
    node_type: "open_question",
    source_tier: 2,
    document_id: "story-doc-2",
    document_title: "Research synthesis · unresolved questions",
    score: 0.88,
  },
];

const meta = {
  title: "Workstation / Write / Field kit",
  component: WriteFieldKit,
  parameters: { layout: "fullscreen" },
  args: { onSelect: () => undefined, initialOpen: true },
  beforeEach: () => {
    const originalFetch = window.fetch;
    window.fetch = async (input) => {
      const url = String(input);
      if (url.includes("/write/folders")) {
        return new Response(JSON.stringify({ folders: [] }), { status: 200 });
      }
      if (url.includes("/write/blocks/search")) {
        return new Response(JSON.stringify({ hits: HITS }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: "not in story fixture" }), { status: 404 });
    };
    return () => {
      window.fetch = originalFetch;
    };
  },
} satisfies Meta<typeof WriteFieldKit>;

export default meta;
type Story = StoryObj<typeof meta>;

export const OpenAtTabletWidth: Story = {};
