import type { Meta, StoryObj } from "@storybook/react";

import ThemeBlockView from "./ThemeBlockView";
import type { ThemeBlock } from "../../../api/themes/by-slug";

/**
 * SPR-11 M7 — Storybook stories for the per-theme block renderer.
 *
 * Three states matter:
 *   - WithBlocks: a promoted highlight_card with full back-link
 *   - Stale: a placeholder for a deleted source block
 *   - Prose: an operator-authored framing block (Tier-3 only)
 */
const meta = {
  title: "Loop 2 / Theme Notebook / ThemeBlockView",
  component: ThemeBlockView,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof ThemeBlockView>;

export default meta;
type Story = StoryObj<typeof meta>;

const promotedHighlight: ThemeBlock = {
  theme_block_id: "tbk-story-1",
  theme_id: "thm-story",
  source_block_id: "blk-source-1",
  source_notebook_id: "nbk-source-1",
  source_document_id: "doc-quantum",
  block_type: "highlight_card",
  content_json: {
    passage_text:
      "Neutral-atom platforms have demonstrated single-qubit gate " +
      "error rates below 10⁻³, consistent with the threshold thesis " +
      "for fault-tolerant operation.",
    chunk_id: "chk-42",
    color: "yellow",
    tag: "fault-tolerance",
    highlight_id: "hl-1",
    operator_framing: "",
  },
  sort_order: 1.0,
  dismissed_at: null,
  created_at: "2026-05-21T10:00:00Z",
  is_stale: false,
  source_notebook_title: "Quantum computing notes",
  source_document_title: "Neutral-atom paper",
};

export const Promoted: Story = {
  args: {
    block: promotedHighlight,
  },
};

export const Stale: Story = {
  args: {
    block: {
      ...promotedHighlight,
      is_stale: true,
      source_notebook_title: null,
    },
  },
};

export const Prose: Story = {
  args: {
    block: {
      ...promotedHighlight,
      theme_block_id: "tbk-story-prose",
      block_type: "prose",
      source_block_id: null,
      source_notebook_id: null,
      source_document_id: null,
      content_json: {
        text:
          "These three highlights all point at the same threshold claim — " +
          "the surrounding context is what makes it the theme's anchor.",
      },
    },
  },
};
