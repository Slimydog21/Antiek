// SPR-06 / M6 — Storybook: Library / WithDocs + Library / Empty
//
// The full library page composing the paste bar, sidebar, and card
// grid. Stories mock the /documents fetch so the chrome renders
// without a live backend.

import type { Meta, StoryObj } from "@storybook/react";

import LibraryGrid from "./LibraryGrid";
import { _resetFoldersForTests } from "../../../api/library/folders";
import { _resetTagsForTests } from "../../../api/library/tags";
import { _resetUserSettingsForTests } from "../../settings/userSettings";

/** Install a window.fetch mock that returns a canned /documents
 * response. Stories install this in their `decorators`. */
function installFetchMock(documents: Array<Record<string, unknown>>) {
  const originalFetch = window.fetch;
  window.fetch = (async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/documents")) {
      return new Response(JSON.stringify({ documents }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.includes("/auth/me")) {
      return new Response(
        JSON.stringify({ user_id: "__operator__", email: null, auth_method: "unauthenticated_local" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    return originalFetch(input, _init);
  }) as typeof window.fetch;
}

const meta = {
  title: "Library",
  component: LibraryGrid,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof LibraryGrid>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Empty: Story = {
  decorators: [
    (Story) => {
      _resetFoldersForTests();
      _resetTagsForTests();
      _resetUserSettingsForTests();
      installFetchMock([]);
      return <Story />;
    },
  ],
};

const SAMPLE_DOCS = [
  {
    document_id: "doc-url-pg-cities",
    title: "Cities and Ambition",
    source_uri: "https://paulgraham.com/cities.html",
    document_type: "web_article",
    source_tier: 4,
    investigation_id: "__operator__",
    content_class: null,
    ip_holder_id: null,
  },
  {
    document_id: "doc-arxiv-1706.03762",
    title: "Attention Is All You Need",
    source_uri: "https://arxiv.org/abs/1706.03762",
    document_type: "academic_paper",
    source_tier: 3,
    investigation_id: "__operator__",
    content_class: null,
    ip_holder_id: null,
  },
  {
    document_id: "doc-url-strat-agg",
    title: "Aggregation Theory",
    source_uri: "https://stratechery.com/2015/aggregation-theory/",
    document_type: "web_article",
    source_tier: 4,
    investigation_id: "__operator__",
    content_class: null,
    ip_holder_id: null,
  },
  {
    document_id: "doc-pdf-fixture",
    title: "Untitled PDF fixture",
    source_uri: "https://example.com/fixture.pdf",
    document_type: "pdf",
    source_tier: 2,
    investigation_id: "__operator__",
    content_class: null,
    ip_holder_id: null,
  },
];

export const WithDocs: Story = {
  decorators: [
    (Story) => {
      _resetFoldersForTests();
      _resetTagsForTests();
      _resetUserSettingsForTests();
      installFetchMock(SAMPLE_DOCS);
      return <Story />;
    },
  ],
};
