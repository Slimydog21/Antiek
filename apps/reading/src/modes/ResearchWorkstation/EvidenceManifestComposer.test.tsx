import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EvidenceManifestComposer from "./EvidenceManifestComposer";

const api = vi.hoisted(() => ({
  create: vi.fn(),
  get: vi.fn(),
  list: vi.fn(),
  launch: vi.fn(),
}));

vi.mock("../../api/research", async (load) => ({
  ...await load<typeof import("../../api/research")>(),
  createEvidenceManifest: api.create,
  getEvidenceManifest: api.get,
  listEvidenceManifests: api.list,
  launchEvidenceManifest: api.launch,
}));

vi.mock("../../hooks/useInvestigation", () => ({ useInvestigation: () => ({}) }));
vi.mock("./ThinkingStream", () => ({ default: () => <div>thinking</div> }));

const collections = ["a", "b"].map((suffix, index) => ({
  collection_id: `dec_${suffix.repeat(32)}`,
  label: `Collection ${index + 1}`,
  derived_asset_id: `ast_${suffix.repeat(32)}`,
  revision_id: `rev_${suffix.repeat(32)}`,
  revision_content_sha256: suffix.repeat(64),
  revision_generation: 1,
  content_sha256: suffix.repeat(64),
  generation: 1,
  version: 1,
  member_count: 2,
  collection_sha256: suffix.repeat(64),
  created_at: "2026-07-16T00:00:00Z",
  updated_at: "2026-07-16T00:00:00Z",
  etag: `"collection-${suffix}"`,
}));

const detail = {
  manifest_id: `dem_${"c".repeat(32)}`,
  label: "Combined evidence",
  version: 1,
  collection_count: 2,
  total_passage_count: 4,
  manifest_sha256: "d".repeat(64),
  created_at: "2026-07-16T00:00:00Z",
  updated_at: "2026-07-16T00:00:00Z",
  collection_refs: collections.map((item, ordinal) => ({
    collection_id: item.collection_id, version: 1,
    collection_sha256: item.collection_sha256, ordinal,
  })),
  collections,
  etag: '"manifest-etag"',
};

describe("EvidenceManifestComposer", () => {
  beforeEach(() => {
    Object.values(api).forEach((mock) => mock.mockReset());
    api.create.mockResolvedValue(detail);
    api.launch.mockResolvedValue({ investigation_id: "inv-child" });
  });

  it("launches once only after the explicit confirmation", async () => {
    render(<MemoryRouter><EvidenceManifestComposer collections={collections} disabled={false} onPendingChange={() => {}} /></MemoryRouter>);
    fireEvent.click(screen.getByLabelText(/Collection 1/));
    fireEvent.click(screen.getByLabelText(/Collection 2/));
    fireEvent.change(screen.getByPlaceholderText("Cross-asset evidence manifest"), { target: { value: "Combined evidence" } });
    fireEvent.click(screen.getByText("Save manifest"));
    await screen.findByText("Research manifest");
    expect(api.launch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Research manifest"));
    fireEvent.change(screen.getByPlaceholderText("What do you want to find out?"), { target: { value: "What connects these sources?" } });
    fireEvent.click(screen.getByText("Confirm launch"));
    await waitFor(() => expect(api.launch).toHaveBeenCalledTimes(1));
    expect(api.launch.mock.calls[0].slice(0, 2)).toEqual([detail.manifest_id, detail.etag]);
  });
});
