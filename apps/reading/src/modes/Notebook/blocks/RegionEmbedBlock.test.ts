import { describe, expect, it, vi } from "vitest";

const { openHostedDocumentPanel } = vi.hoisted(() => ({ openHostedDocumentPanel: vi.fn(() => "panel-id") }));
vi.mock("../../../workspace/actions", () => ({ openHostedDocumentPanel }));

import { openRegionDocument, REGION_RECAPTURE_COPY } from "./RegionEmbedBlock";

describe("RegionEmbedBlock canonical document opening", () => {
  it("preserves canonical document id and page as provenance", () => {
    expect(openRegionDocument("doc-7", 12)).toBe("panel-id");
    expect(openHostedDocumentPanel).toHaveBeenCalledWith({ documentId: "doc-7", page: 12 });
  });

  it("never instructs the operator to open PDF bytes", () => {
    expect(REGION_RECAPTURE_COPY).toMatch(/canonical document/i);
    expect(REGION_RECAPTURE_COPY).not.toMatch(/pdf/i);
  });
});
