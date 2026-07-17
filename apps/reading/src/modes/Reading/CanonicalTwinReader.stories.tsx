import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import CanonicalTwinReader from "./CanonicalTwinReader";
import { json, pendingForever, stubFetch } from "./storyFetch";

const twin = {
  document_id: "twin-doc",
  source_asset_id: "source-a",
  source_hash: "revision-a",
  title: "The swept wing and the transonic threshold",
  html_fragment:
    "<h2>A geometry for a new speed regime</h2><p>Sweeping a wing reduced the component of airflow normal to its leading edge. The technique did not remove compressibility; it changed where and how its effects appeared.</p><h2>What the record supports</h2><p>Wind-tunnel evidence, captured aircraft, and postwar engineering programs converged on the same practical lesson through different paths.</p>",
  authority: "advisory",
  authority_label: "AI-generated advisory notes; verify against sources",
  shareable: false,
  reviewed_promotions_href:
    "/reader/sources/source-a/reviewed-promotions?source_hash=revision-a",
};

const collection = {
  source_asset_id: "source-a",
  source_hash: "revision-a",
  complete: true,
  authority: "current_owner_reviewed_source_promotions_v1",
  items: [
    {
      candidate_id: "candidate-a",
      node_id: "node-a",
      review_id: "review-a",
      kind: "insight",
      text: "Sweep delayed the aerodynamic penalties associated with the transonic regime.",
      evidence_count: 2,
      href: "/reader/promotions/candidate-a",
    },
    {
      candidate_id: "candidate-b",
      node_id: "node-b",
      review_id: "review-b",
      kind: "question",
      text: "How much did German wartime testing accelerate postwar American wing programs?",
      evidence_count: 3,
      href: "/reader/promotions/candidate-b",
    },
  ],
};

const digest = (character: string) => character.repeat(64);
const detail = {
  node: {
    node_id: "node-a", candidate_id: "candidate-a", review_id: "review-a",
    kind: "insight", text: collection.items[0].text, owner_id: "owner-a",
    status: "current", authority: "owner_reviewed_evidence_bound_graph_node_v1",
  },
  citations: [
    {
      citation_id: "citation-twin", node_id: "node-a", owner_id: "owner-a",
      candidate_id: "candidate-a", candidate_digest: digest("a"), review_id: "review-a",
      ordinal: 0, citation_kind: "canonical_twin", document_id: "twin-doc", chunk_id: "twin-chunk",
      range_start: null, range_end: null, text_sha256: digest("b"), chunk_sha256: digest("b"),
      document_sha256: null, source_envelope_sha256: null, content_class: null,
      schema: "antiek.canonical-twin-node-citation.v1",
    },
    ...[1, 2].map((ordinal) => ({
      citation_id: `citation-${ordinal}`, node_id: "node-a", owner_id: "owner-a",
      candidate_id: "candidate-a", candidate_digest: digest("a"), review_id: "review-a",
      ordinal, citation_kind: "evidence", document_id: `source-${ordinal}`, chunk_id: `chunk-${ordinal}`,
      range_start: ordinal * 10, range_end: ordinal * 10 + 8, text_sha256: digest("c"),
      chunk_sha256: digest("d"), document_sha256: digest("e"), source_envelope_sha256: digest("f"),
      content_class: "personal_reading", schema: "antiek.canonical-twin-node-citation.v1",
    })),
  ],
  status: "current",
  authority: "owner_reviewed_evidence_bound_node_citations_v1",
};

function reviewedResponse(url: string) {
  if (url.includes("canonical-twin")) return json(twin);
  if (url.includes("/reader/promotions/")) return json(detail);
  return json(collection);
}

function Frame() {
  return (
    <MemoryRouter initialEntries={["/read/twin/source-a?revision=revision-a"]}>
      <Routes>
        <Route path="/read/twin/:sourceAssetId" element={<CanonicalTwinReader />} />
      </Routes>
    </MemoryRouter>
  );
}

const meta = {
  title: "Read / Canonical twin reader",
  component: Frame,
  parameters: { layout: "fullscreen", router: false },
} satisfies Meta<typeof Frame>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Reviewed: Story = {
  decorators: [stubFetch(reviewedResponse)],
};

export const ExpandedProof: Story = {
  decorators: [stubFetch(reviewedResponse)],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole("button", { name: "2 evidence sources" }));
    await expect(canvas.findByText("Canonical note")).resolves.toBeTruthy();
    await expect(canvas.findAllByText("Source evidence")).resolves.toHaveLength(2);
  },
};

export const Empty: Story = {
  decorators: [
    stubFetch((url) =>
      url.includes("canonical-twin") ? json(twin) : json({ ...collection, items: [] }),
    ),
  ],
};

export const Loading: Story = { decorators: [stubFetch(pendingForever)] };

export const Unavailable: Story = {
  decorators: [stubFetch(() => json({ detail: "unavailable" }, 503))],
};
