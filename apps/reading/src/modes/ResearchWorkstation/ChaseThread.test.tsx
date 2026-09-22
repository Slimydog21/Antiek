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
    sourcePolicy: [],
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
import {
  clearChaseDraftHandoffs,
  listChaseDraftHandoffs,
} from "./chaseHandoffs";

afterEach(() => {
  cleanup();
  startInvestigationMock.mockReset();
  navigateMock.mockReset();
  recordSpawnMock.mockReset();
  clearChaseDraftHandoffs();
});

function renderChase(props: {
  spawnContext: string;
  parentInvestigationId: string;
  reservedChildId?: string | null;
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
    await waitFor(() =>
      expect(listChaseDraftHandoffs("inv-parent")[0]).toMatchObject({
        child_investigation_id: "inv-fresh",
        parent_investigation_id: "inv-parent",
        source_passage: "an unflagged passage",
        no_spend: true,
      }),
    );
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

describe("ChaseThread — draft handoff receipt", () => {
  it("copies a no-spend handoff that connects the launched child back to its parent and passage", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    startInvestigationMock.mockResolvedValue({
      investigation_id: "inv-child",
      status: "in_progress",
      start_event_id: "e3",
    });
    renderChase({
      spawnContext: "wing sweep delayed transonic drag rise",
      parentInvestigationId: "read-doc-1",
    });

    fireEvent.click(screen.getByText("Follow this"));
    await waitFor(() => expect(screen.getByText(/following the thread/)).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /copy handoff/i }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const payload = JSON.parse(writeText.mock.calls[0][0]);
    expect(payload).toMatchObject({
      kind: "antiek.chase.draft_handoff",
      child_investigation_id: "inv-child",
      parent_investigation_id: "read-doc-1",
      source_passage: "wing sweep delayed transonic drag rise",
      no_spend: true,
    });
    expect(payload.next_step).toMatch(/compose it with its parent/);
    expect(screen.getByRole("button", { name: /copied/i })).toBeTruthy();
  });
});
