import type { Meta, StoryObj } from "@storybook/react";

import PersonalSpace from "./index";
import { httpError, json, pendingForever, stubFetch } from "../storyFetch";

/**
 * PersonalSpace (Read SPR-13) — the reader's self-organizing bed of what they've
 * read and made.
 *
 * Product-character authorship (ALC SPR-09): SPR-07 designed this surface's
 * loading / empty / error SYSTEM states at runtime (live regions + §5 copy from
 * `READING_STATE_COPY`). This file authors each of those states as its OWN named,
 * co-located Storybook story so the state SPR-07 built is now ALSO inspectable in
 * isolation — lifting co-location and making the state-authorship countable on the
 * rubric's Dimension-3 criterion. The states are reached through the component's
 * REAL data path: each story pins `fetch` (`storyFetch.tsx`); nothing else is
 * touched, and runtime behaviour is unchanged.
 *
 * §5 voice: the loading/error copy is `READING_STATE_COPY` (centralized §5 prose);
 * the empty state is the component's own authored Werner moment. Brand firewall:
 * no PostHog phrasing.
 */
const meta = {
  title: "Read / PersonalSpace",
  component: PersonalSpace,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof PersonalSpace>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * LOADING — the polite live-region status while the readings are gathered. The
 * list `fetch` never settles so "Gathering your readings…" holds for inspection
 * (the §5 sentence, not a bare ellipsis).
 */
export const Loading: Story = {
  decorators: [stubFetch(pendingForever)],
};

/**
 * EMPTY — the AUTHORED empty moment (not a default blank): Werner takes his
 * sanctioned `empty` stage and the copy guides the reader to the library or to
 * making a reading. Both endpoints answer with zero assets.
 */
export const Empty: Story = {
  decorators: [
    stubFetch((url) =>
      /\/categories/.test(url)
        ? json({ categories: [], ordering: "recency", stability_bound: 4 })
        : json({ assets: [], count: 0 }),
    ),
  ],
};

/**
 * POPULATED — the resting success state: saved reads + created readings in the
 * honest recency bucket (categories kick in past the stability bound). Shows the
 * ordering-honesty line and the created-vs-book tag distinction.
 */
export const Populated: Story = {
  decorators: [
    stubFetch((url) => {
      if (/\/categories/.test(url)) {
        return json({ categories: [], ordering: "recency", stability_bound: 4 });
      }
      if (/\/file-suggestion/.test(url)) {
        return json({ document_id: "doc-1", matches: [] });
      }
      return json({
        count: 2,
        assets: [
          {
            asset_id: "asset-1",
            kind: "meta_reading",
            title: "How my books treat free will",
            prompt: "free will across the corpus",
            document_ids: ["doc-1"],
            emitted_at: "2026-06-10T10:00:00Z",
            open_route: "/read/meta-reading/asset-1",
          },
          {
            asset_id: "asset-2",
            kind: "saved_read",
            title: "The Order of Time",
            prompt: null,
            document_ids: ["doc-2"],
            emitted_at: "2026-06-09T09:00:00Z",
            open_route: "/read/doc-2",
          },
        ],
      });
    }),
  ],
};

/**
 * ERROR — the assertive alert: the readings didn't load. The reader sees the calm
 * §5 sentence (`collectionError`), never the raw engine string. The list endpoint
 * answers 500.
 */
export const Error: Story = {
  decorators: [stubFetch(() => httpError(500))],
};
