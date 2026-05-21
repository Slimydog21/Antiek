// SPR-06 / M6 — Storybook: LibraryCard / Default + Reading
//
// Variants exercised:
//   - Default: HTML article, never opened, no progress bar.
//   - Reading: PDF, opened 2 hours ago, halfway progress.
//   - Paywalled: HTML article with metadata.paywalled = true. The
//     partial tag must be visible (rigor #1).
//   - WithTags: tag chips revealed on hover (always visible in
//     Storybook so the chip shape is reviewable).

import type { Meta, StoryObj } from "@storybook/react";

import { LibraryCard } from "./LibraryCard";

const meta = {
  title: "LibraryCard",
  component: LibraryCard,
  parameters: {
    layout: "centered",
  },
  decorators: [
    (Story) => (
      <div style={{ width: 260 }}>
        <Story />
      </div>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof LibraryCard>;

export default meta;
type Story = StoryObj<typeof meta>;

const baseHtmlDoc = {
  document_id: "doc-url-abc123",
  title: "Cities and Ambition",
  source_uri: "https://paulgraham.com/cities.html",
  document_type: "web_article",
  source_tier: 4,
  metadata: { content_type: "html_article" },
};

const basePdfDoc = {
  document_id: "doc-pdf-xyz789",
  title: "Attention Is All You Need",
  source_uri: "https://arxiv.org/pdf/1706.03762",
  document_type: "pdf",
  source_tier: 3,
  metadata: { content_type: "pdf" },
};

export const Default: Story = {
  args: {
    doc: baseHtmlDoc,
  },
};

export const Reading: Story = {
  args: {
    doc: {
      ...basePdfDoc,
      last_read_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
      read_progress: 0.42,
    },
  },
};

export const Paywalled: Story = {
  args: {
    doc: {
      ...baseHtmlDoc,
      title: "Some paywalled NYT article",
      source_uri: "https://nytimes.com/some-paywalled",
      metadata: { content_type: "html_article", paywalled: true },
    },
  },
};

export const WithTags: Story = {
  args: {
    doc: baseHtmlDoc,
    tagNames: ["read-later", "essay", "founder-blogs"],
  },
};
