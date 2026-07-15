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

const { startInvestigationMock, navigateMock, recordSpawnMock } = vi.hoisted(
  () => ({
    startInvestigationMock: vi.fn(),
    navigateMock: vi.fn(),
    recordSpawnMock: vi.fn(),
  }),
);

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
  };
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
      },
    });
    fireEvent.click(screen.getByText("Follow this"));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(1));
    const arg = startInvestigationMock.mock.calls[0][0];
    expect(arg.spawn_context).toBe("A selected canonical passage");
    expect(arg.context).toContain(`"revision_id":"rev_${"b".repeat(32)}"`);
    expect(arg.context).toContain(`"generation":7`);
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
