import type { Meta, StoryObj } from "@storybook/react";

import type { BookSummary } from "../../api/books";
import realCover from "../../brand/werner/marks/social-card-1200.png";
import BookCard from "./BookCard";

const base: BookSummary = {
  document_id: "doc-book-1",
  title: "Meditations",
  author: "Marcus Aurelius",
  servability: "public_domain",
  servable_full_text: true,
  page_count: 254,
  cover_uri: null,
  ip_holder_id: null,
  taken_down: false,
};

const meta = {
  title: "Read / BookCard",
  component: BookCard,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
} satisfies Meta<typeof BookCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const PublicDomain: Story = { args: { book: base } };

export const PublisherLicensed: Story = {
  args: { book: { ...base, title: "Deep Learning", author: "Goodfellow et al.", servability: "publisher_opted_in" } },
};

export const PreviewOnlyGated: Story = {
  args: {
    book: {
      ...base,
      title: "A Copyrighted Title We Only Preview",
      author: "Unknown",
      servability: "gated_metadata_only",
      servable_full_text: false,
    },
  },
};

export const AntiekOriginal: Story = {
  args: { book: { ...base, title: "An Antiek-Authored Book", servability: "platform_authored" } },
};

export const LongTitleFallback: Story = {
  args: {
    book: {
      ...base,
      document_id: "long-form-archive-title",
      title: "The Polar Archive and the Shape of Memory Across Many Generations",
      cover_uri: null,
    },
  },
};

export const RealCoverAuthority: Story = {
  args: {
    book: {
      ...base,
      cover_uri: realCover,
    },
  },
};

/** The shelf: a grid of mixed servability, the way Library renders them. */
export const Shelf: Story = {
  render: () => (
    <div
      className="grid gap-5 p-6"
      style={{ gridTemplateColumns: "repeat(4, 140px)" }}
    >
      <BookCard book={base} />
      <BookCard book={{ ...base, document_id: "d2", title: "Deep Learning", servability: "publisher_opted_in" }} />
      <BookCard book={{ ...base, document_id: "d3", title: "Preview Title", servability: "gated_metadata_only", servable_full_text: false }} />
      <BookCard book={{ ...base, document_id: "d4", title: "An Antiek Original", servability: "platform_authored" }} />
    </div>
  ),
};
