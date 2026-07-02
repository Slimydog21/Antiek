/**
 * researchSuggestion.promotion.test.ts — Read → Research explicit promotion.
 *
 * Promotion launches a new investigation and records its id into the seam
 * event. That returned id is an API boundary and must be sanitized before it
 * becomes an audit link or caller-visible result.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { acceptPromotion, suggestPromotion } from "./researchSuggestion";

const { postTypedEventMock, startInvestigationMock } = vi.hoisted(() => ({
  postTypedEventMock: vi.fn(),
  startInvestigationMock: vi.fn(),
}));

vi.mock("./api", async (orig) => {
  const actual = await orig<typeof import("./api")>();
  return {
    ...actual,
    postTypedEvent: postTypedEventMock,
    startInvestigation: startInvestigationMock,
  };
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("suggestPromotion (pure)", () => {
  it("returns null for an empty prompt or empty source corpus", () => {
    expect(suggestPromotion({ prompt: "   ", corpusDocumentIds: ["doc-1"] })).toBeNull();
    expect(suggestPromotion({ prompt: "What matters?", corpusDocumentIds: [] })).toBeNull();
    expect(postTypedEventMock).not.toHaveBeenCalled();
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });

  it("shapes a suggestion without launching research", () => {
    const suggestion = suggestPromotion({
      prompt: "  What matters?  ",
      corpusDocumentIds: ["doc-1", "doc-2"],
    });

    expect(suggestion).toEqual({
      question: "What matters?",
      rationale: "This reading drew on 2 of your books. Want to chase it further as a full research?",
    });
    expect(postTypedEventMock).not.toHaveBeenCalled();
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });
});

describe("acceptPromotion", () => {
  it("trims promotion inputs and the launched investigation id before recording the seam event", async () => {
    startInvestigationMock.mockResolvedValue({
      investigation_id: " inv-promoted ",
      status: "in_progress",
      start_event_id: "e1",
    });
    postTypedEventMock.mockResolvedValue({
      event_id: "ev-1",
      action_type: "seam.read_to_research",
    });

    const result = await acceptPromotion({
      assetId: " asset-1 ",
      prompt: " What matters? ",
      documentId: " doc-1 ",
    });

    expect(result).toEqual({ investigation_id: "inv-promoted" });
    expect(startInvestigationMock).toHaveBeenCalledWith({
      question: "What matters?",
      context: "Promoted from a meta-reading asset (Read → Research).",
      spawn_context: "read-meta-asset:asset-1",
    });
    expect(postTypedEventMock).toHaveBeenCalledTimes(1);
    expect(postTypedEventMock.mock.calls[0][0]).toMatchObject({
      investigation_id: "inv-promoted",
      document_id: "doc-1",
      payload: {
        entity_id: "read-meta-asset:asset-1",
        provenance_ref: "asset-1",
        document_id: "doc-1",
        launched_investigation_id: "inv-promoted",
      },
    });
  });

  it("rejects malformed promotion inputs before launching research or emitting a seam event", async () => {
    await expect(
      acceptPromotion({
        assetId: " ",
        prompt: "What matters?",
        documentId: "doc-1",
      }),
    ).rejects.toThrow(/assetId/);
    await expect(
      acceptPromotion({
        assetId: "asset-1",
        prompt: " ",
        documentId: "doc-1",
      }),
    ).rejects.toThrow(/prompt/);
    await expect(
      acceptPromotion({
        assetId: "asset-1",
        prompt: "What matters?",
        documentId: " ",
      }),
    ).rejects.toThrow(/documentId/);

    expect(startInvestigationMock).not.toHaveBeenCalled();
    expect(postTypedEventMock).not.toHaveBeenCalled();
  });

  it("rejects malformed launched ids before emitting a seam event", async () => {
    startInvestigationMock.mockResolvedValue({
      investigation_id: " ",
      status: "in_progress",
      start_event_id: "e1",
    });

    await expect(
      acceptPromotion({
        assetId: "asset-1",
        prompt: "What matters?",
        documentId: "doc-1",
      }),
    ).rejects.toThrow("investigation_id must be a non-empty string");
    expect(postTypedEventMock).not.toHaveBeenCalled();
  });
});
