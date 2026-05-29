import type { Meta, StoryObj } from "@storybook/react";

import type { BookSummary } from "../../api/books";
import WorkCard from "./WorkCard";

const base: BookSummary = {
  document_id: "doc-work-1",
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
  title: "Read / Library / WorkCard",
  component: WorkCard,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
} satisfies Meta<typeof WorkCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Servable: Story = { args: { work: base } };

export const PublisherLicensed: Story = {
  args: {
    work: {
      ...base,
      title: "Deep Learning",
      author: "Goodfellow et al.",
      servability: "publisher_opted_in",
    },
  },
};

export const GatedPreview: Story = {
  args: {
    work: {
      ...base,
      title: "A Copyrighted Title We Only Catalog",
      author: "Unknown",
      servability: "gated_metadata_only",
      servable_full_text: false,
      page_count: 0,
      ip_holder_id: "ip-acme",
    },
  },
};

export const Removed: Story = {
  args: {
    work: {
      ...base,
      title: "A Removed Title",
      servability: "taken_down",
      servable_full_text: false,
      taken_down: true,
    },
  },
};
