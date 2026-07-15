/**
 * ChaseThread.test.tsx — follow a highlight into a child research (SPR-04
 * M2).
 *
 * Pins the load-bearing gates:
 *   - CHASE REUSES THE RESERVED ID: when the passage maps to an SPR-03
 *     escalated question (a reserved child id is present), the launch goes
 *     INTO that id (passed as investigation_id) — no orphan, no rogue
 *     second child;
 *   - FRESH MINT otherwise: a raw highlight (no reserved id) launches
 *     WITHOUT investigation_id, so the substrate mints a fresh child
 *     parented to the current research;
 *   - NO AUTO-SPAWN: mounting the panel launches nothing — a launch
 *     happens only on the explicit "Follow this" click;
 *   - HONEST NO-KEY: a failed launch shows the shared AIActionFailure, not
 *     a fabricated child.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const { startInvestigationMock, launchCollectionMock, launchManifestMock, navigateMock, recordSpawnMock } = vi.hoisted(
  () => ({
    startInvestigationMock: vi.fn(),
    launchCollectionMock: vi.fn(),
    launchManifestMock: vi.fn(),
    navigateMock: vi.fn(),
    recordSpawnMock: vi.fn(),
  }),
);

vi.mock("../../api/research", async (orig) => {
  const actual = await orig<typeof import("../../api/research")>();
  return { ...actual, launchDerivedEvidenceCollection: launchCollectionMock, launchEvidenceManifest: launchManifestMock };
});

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, startInvestigation: startInvestigationMock };
});
vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});
vi.mock("../../hooks/useInvestigationTree", () => ({
  recordSpawnRelationship: recordSpawnMock,
}));
// The launched-thread view reads the live stream; stub at the hook
// boundary so jsdom needs no socket. Return a COMPLETE InvestigationState
// (ThinkingStream reads costTotal.toFixed) so the post-launch render is
// clean rather than throwing on a partial mock.
vi.mock("../../hooks/useInvestigation", () => ({
  useInvestigation: () => ({
    id: "inv-child",
    status: "in_progress",
    question: null,
    events: [],
    terminalPayload: null,
    costTotal: 0,
    completedAt: null,
    streamStatus: "open",
    reconnects: 0,
  }),
}));
// The Werner beat is decoration; render it inert.
vi.mock("../../shared/delight", () => ({
  CelebrateBurst: () => null,
  useCelebrate: () => ({ celebrating: false, celebrate: vi.fn() }),
}));
// Voice capture is its own unit (VoiceChaseButton); stub it here.
vi.mock("./VoiceChaseButton", () => ({ default: () => null }));

import ChaseThread from "./ChaseThread";
import { ApiError } from "../../lib/api";

afterEach(() => {
  cleanup();
  startInvestigationMock.mockReset();
  navigateMock.mockReset();
  recordSpawnMock.mockReset();
  launchCollectionMock.mockReset();
  launchManifestMock.mockReset();
});

function renderChase(props: {
  spawnContext: string;
  parentInvestigationId: string;
  reservedChildId?: string | null;
  sourceProvenance?: {
    documentId: string;
    derivedRevisionId: string;
    derivedContentSha256: string;
    derivedGeneration: number;
    derivedCitationId?: string;
    derivedChunkOrdinal?: number;
    derivedChunkTextSha256?: string;
  };
  sourceSelections?: Array<{
    text: string;
    provenance: {
      documentId: string;
      derivedRevisionId: string;
      derivedContentSha256: string;
      derivedGeneration: number;
      derivedCitationId: string;
      derivedChunkOrdinal: number;
      derivedChunkTextSha256: string;
    };
  }>;
  evidenceCollection?: { collectionId: string; etag: string };
  evidenceManifest?: { manifestId: string; etag: string };
}) {
  return render(
    <MemoryRouter>
      <ChaseThread {...props} />
    </MemoryRouter>,
  );
}

describe("ChaseThread — reserved-id reuse (M2)", () => {
  it("launches INTO the reserved escalation id when present (no orphan)", async () => {
    startInvestigationMock.mockResolvedValue({
      investigation_id: "inv-reserved",
      status: "in_progress",
      start_event_id: "e1",
    });
    renderChase({
      spawnContext: "margins compress at scale",
      parentInvestigationId: "inv-parent",
      reservedChildId: "inv-reserved",
    });
    // No launch on mount.
    expect(startInvestigationMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText("Follow this"));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(1));
    const arg = startInvestigationMock.mock.calls[0][0];
    // The reserved id is consumed as investigation_id — one research per
    // question, not a rogue second child.
    expect(arg.investigation_id).toBe("inv-reserved");
    expect(arg.parent_investigation_id).toBe("inv-parent");
    expect(arg.spawn_context).toBe("margins compress at scale");
    expect(recordSpawnMock).toHaveBeenCalledWith("inv-reserved", "inv-parent");
  });

  it("mints a FRESH child (no investigation_id) for a raw highlight", async () => {
    startInvestigationMock.mockResolvedValue({
      investigation_id: "inv-fresh",
      status: "in_progress",
      start_event_id: "e2",
    });
    renderChase({
      spawnContext: "an unflagged passage",
      parentInvestigationId: "inv-parent",
      // no reservedChildId
    });
    fireEvent.click(screen.getByText("Follow this"));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(1));
    const arg = startInvestigationMock.mock.calls[0][0];
    // No reserved id ⇒ no investigation_id ⇒ substrate mints fresh.
    expect(arg.investigation_id).toBeUndefined();
    expect(arg.parent_investigation_id).toBe("inv-parent");
  });

  it("persists exact derived HTML provenance in child research context", async () => {
    startInvestigationMock.mockResolvedValue({
      investigation_id: "inv-derived", status: "in_progress", start_event_id: "e3",
    });
    renderChase({
      spawnContext: "A selected canonical passage",
      parentInvestigationId: "read-asset",
      sourceProvenance: {
        documentId: `ast_${"a".repeat(32)}`,
        derivedRevisionId: `rev_${"b".repeat(32)}`,
        derivedContentSha256: "c".repeat(64),
        derivedGeneration: 7,
        derivedCitationId: `dchunk_${"d".repeat(64)}`,
        derivedChunkOrdinal: 3,
        derivedChunkTextSha256: "e".repeat(64),
      },
    });
    fireEvent.click(screen.getByText("Follow this"));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(1));
    const arg = startInvestigationMock.mock.calls[0][0];
    expect(arg.spawn_context).toBe("A selected canonical passage");
    expect(arg.context).toBe("A selected canonical passage");
    expect(arg.derived_source).toEqual({
      derived_asset_id: `ast_${"a".repeat(32)}`,
      revision_id: `rev_${"b".repeat(32)}`,
      content_sha256: "c".repeat(64),
      generation: 7,
      citation_id: `dchunk_${"d".repeat(64)}`,
      chunk_ordinal: 3,
      chunk_text_sha256: "e".repeat(64),
      excerpt: "A selected canonical passage",
    });
  });

  it("launches one ordered investigation from several exact passages", async () => {
    startInvestigationMock.mockResolvedValue({
      investigation_id: "inv-curated", status: "in_progress", start_event_id: "e4",
    });
    const passages = ["First exact passage", "Second exact passage"];
    const spawnContext = passages.map(
      (text, index) => `[Evidence ${index + 1} of 2]\n${text}`,
    ).join("\n\n");
    const sourceSelections = passages.map((text, index) => ({
      text,
      provenance: {
        documentId: `ast_${"a".repeat(32)}`,
        derivedRevisionId: `rev_${"b".repeat(32)}`,
        derivedContentSha256: "c".repeat(64),
        derivedGeneration: 7,
        derivedCitationId: `dchunk_${String(index + 1).repeat(64)}`,
        derivedChunkOrdinal: index,
        derivedChunkTextSha256: String(index + 3).repeat(64),
      },
    }));
    renderChase({
      spawnContext, parentInvestigationId: "read-asset", sourceSelections,
    });
    expect(startInvestigationMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Follow this"));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(1));
    const arg = startInvestigationMock.mock.calls[0][0];
    expect(arg.context).toBe(spawnContext);
    expect(arg.derived_source).toBeUndefined();
    expect(arg.derived_sources.map((source: { excerpt: string }) => source.excerpt))
      .toEqual(passages);
  });

  it("launches restored evidence by collection authority only after confirmation", async () => {
    launchCollectionMock.mockResolvedValue({
      investigation_id: "inv-saved", status: "started", start_event_id: "e5",
    });
    const sourceSelections = [0, 1].map((index) => ({
      text: `Passage ${index + 1}`,
      provenance: {
        documentId: `ast_${"a".repeat(32)}`,
        derivedRevisionId: `rev_${"b".repeat(32)}`,
        derivedContentSha256: "c".repeat(64), derivedGeneration: 2,
        derivedCitationId: `dchunk_${String(index + 1).repeat(64)}`,
        derivedChunkOrdinal: index,
        derivedChunkTextSha256: String(index + 3).repeat(64),
      },
    }));
    renderChase({
      spawnContext: "[Evidence 1 of 2]\nPassage 1\n\n[Evidence 2 of 2]\nPassage 2",
      parentInvestigationId: "read-saved",
      sourceSelections,
      evidenceCollection: { collectionId: `dec_${"d".repeat(32)}`, etag: '"etag"' },
    });
    expect(launchCollectionMock).not.toHaveBeenCalled();
    const followButton = screen.getByText("Follow this");
    fireEvent.click(followButton);
    fireEvent.click(followButton);
    await waitFor(() => expect(launchCollectionMock).toHaveBeenCalledTimes(1));
    expect(startInvestigationMock).not.toHaveBeenCalled();
    expect(launchCollectionMock.mock.calls[0].slice(0, 2)).toEqual([
      `dec_${"d".repeat(32)}`, '"etag"',
    ]);
    expect(launchCollectionMock.mock.calls[0][3]).toEqual({
      question: "[Evidence 1 of 2]\nPassage 1\n\n[Evidence 2 of 2]\nPassage 2",
      parent_investigation_id: "read-saved",
    });
  });

  it("does not downgrade a malformed citation into an unverified launch", async () => {
    renderChase({
      spawnContext: "A selected canonical passage",
      parentInvestigationId: "read-asset",
      sourceProvenance: {
        documentId: `ast_${"a".repeat(32)}`,
        derivedRevisionId: `rev_${"b".repeat(32)}`,
        derivedContentSha256: "c".repeat(64),
        derivedGeneration: 7,
        derivedCitationId: "malformed",
        derivedChunkOrdinal: 3,
        derivedChunkTextSha256: "e".repeat(64),
      },
    });
    fireEvent.click(screen.getByText("Follow this"));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain(
      "This citation could not be verified for research.",
    ));
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });

  it("does not downgrade derived revision provenance missing citation fields", async () => {
    renderChase({
      spawnContext: "A selected canonical passage",
      parentInvestigationId: "read-asset",
      sourceProvenance: {
        documentId: `ast_${"a".repeat(32)}`,
        derivedRevisionId: `rev_${"b".repeat(32)}`,
        derivedContentSha256: "c".repeat(64),
        derivedGeneration: 7,
      },
    });
    fireEvent.click(screen.getByText("Follow this"));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain(
      "This citation could not be verified for research.",
    ));
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });
});

describe("ChaseThread — no auto-spawn (M2)", () => {
  it("launches nothing until the explicit gesture", () => {
    renderChase({
      spawnContext: "a passage",
      parentInvestigationId: "inv-parent",
      reservedChildId: "inv-reserved",
    });
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });
});

describe("ChaseThread — honest no-key (M4)", () => {
  it("shows the failure surface on a failed launch, no fabricated child", async () => {
    startInvestigationMock.mockImplementation(async () => {
      throw new ApiError("no provider", 503, "no model configured");
    });
    renderChase({
      spawnContext: "a passage",
      parentInvestigationId: "inv-parent",
    });
    fireEvent.click(screen.getByText("Follow this"));
    await waitFor(() =>
      expect(screen.getByText(/Couldn.t follow this thread/)).toBeTruthy(),
    );
    // Did NOT transition to a launched child.
    expect(screen.queryByText(/following the thread/)).toBeNull();
  });
});

describe("ChaseThread — Cycle 71 manifest-authoritative launch", () => {
  it("uses launchEvidenceManifest when evidenceManifest prop is present", async () => {
    launchManifestMock.mockResolvedValue({
      investigation_id: "inv-manifest", status: "started", start_event_id: "evt-manifest",
    });
    renderChase({
      spawnContext: "What patterns exist across assets?",
      parentInvestigationId: "inv-parent",
      evidenceManifest: { manifestId: `dem_${"a".repeat(32)}`, etag: '"manifest-etag"' },
    });
    expect(launchManifestMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Follow this"));
    await waitFor(() => expect(launchManifestMock).toHaveBeenCalledTimes(1));
    // startInvestigation is NOT called — manifest path is exclusive.
    expect(startInvestigationMock).not.toHaveBeenCalled();
    expect(launchCollectionMock).not.toHaveBeenCalled();
    // If-Match etag is forwarded.
    expect(launchManifestMock.mock.calls[0][1]).toBe('"manifest-etag"');
    // Body sends only question + parent — no context, no sources, no provider.
    expect(launchManifestMock.mock.calls[0][3]).toEqual({
      question: "What patterns exist across assets?",
      parent_investigation_id: "inv-parent",
    });
  });

  it("sends no context, sources, or spawn_context in manifest launch", async () => {
    launchManifestMock.mockResolvedValue({
      investigation_id: "inv-manifest2", status: "started", start_event_id: "evt-m2",
    });
    renderChase({
      spawnContext: "Cross-asset analysis question",
      parentInvestigationId: "inv-parent",
      evidenceManifest: { manifestId: `dem_${"b".repeat(32)}`, etag: '"etag2"' },
    });
    fireEvent.click(screen.getByText("Follow this"));
    await waitFor(() => expect(launchManifestMock).toHaveBeenCalledTimes(1));
    const body = launchManifestMock.mock.calls[0][3];
    // Per spec: "Accept no context, collection array, source array, provider, model, spend, asset, revision, or digest."
    expect(body.context).toBeUndefined();
    expect(body.collection_ids).toBeUndefined();
    expect(body.sources).toBeUndefined();
    expect(body.provider).toBeUndefined();
    expect(body.model).toBeUndefined();
    expect(body.spawn_context).toBeUndefined();
  });

  it("does not auto-launch on mount when manifest prop is present", () => {
    renderChase({
      spawnContext: "a passage",
      parentInvestigationId: "inv-parent",
      evidenceManifest: { manifestId: `dem_${"c".repeat(32)}`, etag: '"etag"' },
    });
    expect(launchManifestMock).not.toHaveBeenCalled();
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });

  it("shows failure surface on manifest launch error", async () => {
    launchManifestMock.mockImplementation(async () => {
      throw new ApiError("manifest stale", 412, "ETag mismatch");
    });
    renderChase({
      spawnContext: "a question",
      parentInvestigationId: "inv-parent",
      evidenceManifest: { manifestId: `dem_${"d".repeat(32)}`, etag: '"stale-etag"' },
    });
    fireEvent.click(screen.getByText("Follow this"));
    await waitFor(() =>
      expect(screen.getByText(/Couldn.t follow this thread/)).toBeTruthy(),
    );
    expect(screen.queryByText(/following the thread/)).toBeNull();
  });
});
