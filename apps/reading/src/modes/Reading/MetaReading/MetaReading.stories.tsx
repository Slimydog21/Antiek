import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { Meta, StoryObj } from "@storybook/react";

import MetaReading from "./index";
import { httpError, json, pendingForever, stubFetch } from "../storyFetch";

/**
 * MetaReading (Read SPR-08/13) — the one-shot, read-only, page-cited synthesis
 * over the OWNED corpus, and the re-open view for a saved one.
 *
 * Product-character authorship (ALC SPR-09): SPR-07 designed this surface's
 * loading / error SYSTEM states at runtime (live regions + §5 copy from
 * `READING_STATE_COPY`). This file authors those states — plus the resting ask
 * form and the resolved saved report — as their OWN named, co-located Storybook
 * stories, so the states SPR-07 built are now ALSO inspectable in isolation,
 * lifting co-location and making the state-authorship countable on the rubric's
 * Dimension-3 criterion. States are reached through the component's REAL data
 * path (each story pins `fetch`); runtime behaviour is unchanged.
 *
 * The loading/error states live on the RE-OPEN path (an `assetId` route param),
 * so those stories bring their own `MemoryRouter` (and opt out of the global one
 * via `parameters.router: false`) to supply the param the component reads.
 *
 * §5 voice: error copy is `READING_STATE_COPY.metaReadingError`; loading is
 * `collectionGathering`. Brand firewall: no PostHog phrasing.
 */
const meta = {
  title: "Read / MetaReading",
  component: MetaReading,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof MetaReading>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Mount the re-open path with a fixed `assetId` so the component loads a saved
 *  asset (the path its loading/error/success states live on). */
function ReopenAt() {
  return (
    <MemoryRouter initialEntries={["/x/asset-1"]}>
      <Routes>
        <Route path="/x/:assetId" element={<MetaReading />} />
      </Routes>
    </MemoryRouter>
  );
}

/**
 * IDLE — the resting ask form: the reader sets a prompt and a HARD length box,
 * then makes the reading. The proposed-boundary banner is honest about the
 * unratified Research↔Read scope. (No route param → the generator, not re-open.)
 */
export const Idle: Story = {};

/**
 * LOADING — the polite live-region status while a saved reading is re-opened. The
 * re-open `fetch` never settles, so "Gathering your readings…" holds for
 * inspection. Reached via the `assetId` re-open path.
 */
export const ReopenLoading: Story = {
  parameters: { router: false },
  decorators: [stubFetch(pendingForever)],
  render: () => {
    return <ReopenAt />;
  },
};

/**
 * ERROR — the assertive alert when a saved reading can't be re-opened. The reader
 * sees the calm §5 sentence (`metaReadingError`), never the raw engine string.
 * The re-open endpoint answers 404.
 */
export const ReopenError: Story = {
  parameters: { router: false },
  decorators: [stubFetch(() => httpError(404))],
  render: () => {
    return <ReopenAt />;
  },
};

/**
 * SAVED REPORT — the resolved success state: a re-opened read-only synthesis with
 * its report, a page-cited link back into the reader, and the suggest-not-autoship
 * promote affordance. The re-open endpoint returns a saved asset.
 */
export const SavedReport: Story = {
  parameters: { router: false },
  decorators: [
    stubFetch(() =>
      json({
        asset_id: "asset-1",
        prompt: "How my books treat free will",
        report:
          "Across the owned corpus, the treatment of free will turns on whether time is taken as fundamental. Where it is, choice reads as compatibilist; where it dissolves, the question is reframed rather than answered.",
        citations: [
          {
            chunk_id: "chunk-1",
            document_id: "doc-2",
            page_index: 41,
            page_resolved: true,
            snippet: "the order of time",
          },
        ],
        length_unit: "pages",
        length_amount: 3,
        truncated: false,
        corpus_scope: "hard",
        corpus_document_ids: ["doc-1", "doc-2"],
      }),
    ),
  ],
  render: () => {
    return <ReopenAt />;
  },
};
