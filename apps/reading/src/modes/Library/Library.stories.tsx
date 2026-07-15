import type { Meta, StoryObj } from "@storybook/react";

import type { BookSummary } from "../../api/books";
import Library from "./index";

const books: BookSummary[] = [
  {
    document_id: "meditations",
    title: "Meditations",
    author: "Marcus Aurelius",
    servability: "public_domain",
    servable_full_text: true,
    page_count: 254,
    cover_uri: null,
    ip_holder_id: null,
    taken_down: false,
  },
  {
    document_id: "field-notes",
    title: "Field Notes on Distributed Systems",
    author: "Antiek Research",
    servability: "platform_authored",
    servable_full_text: true,
    page_count: 91,
    cover_uri: null,
    ip_holder_id: null,
    taken_down: false,
  },
  {
    document_id: "polar-archive",
    title: "The Polar Archive and the Shape of Memory",
    author: "Mara Voss",
    servability: "publisher_opted_in",
    servable_full_text: true,
    page_count: 318,
    cover_uri: null,
    ip_holder_id: "publisher-voss",
    taken_down: false,
  },
];

const noInvestigations = async () => ({ count: 0, investigations: [] });

const meta = {
  title: "Read / Library / Archive shelf",
  component: Library,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof Library>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Populated: Story = {
  args: {
    loadBooks: async () => ({ books, count: books.length }),
    loadInvestigations: noInvestigations,
  },
};

export const EmptyShelf: Story = {
  args: {
    loadBooks: async () => ({ books: [], count: 0 }),
    loadInvestigations: noInvestigations,
  },
};

export const Loading: Story = {
  args: {
    loadBooks: () => new Promise(() => {}),
    loadInvestigations: noInvestigations,
  },
};

export const Error: Story = {
  args: {
    loadBooks: async () => { throw new Error("fixture unavailable"); },
    loadInvestigations: noInvestigations,
  },
};
