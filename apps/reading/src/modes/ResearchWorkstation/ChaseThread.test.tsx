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

const { startInvestigationMock, launchReservedQuestionMock, navigateMock, recordSpawnMock } = vi.hoisted(
  () => ({
    startInvestigationMock: vi.fn(),
    launchReservedQuestionMock: vi.fn(),
    navigateMock: vi.fn(),
    recordSpawnMock: vi.fn(),
  }),
);

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    startInvestigation: startInvestigationMock,
    launchReservedQuestion: launchReservedQuestionMock,
  };
});
vi.mock("../../components/engagement/ResearchRunCeilingApproval", async () => {
  const { useLayoutEffect } = await import("react");
  return {
    ResearchRunCeilingApproval: ({ onAuthorizationChange }: { onAuthorizationChange: (value: unknown) => void }) => {
      useLayoutEffect(() => {
        onAuthorizationChange({ approved: true, ceilingUsd: 1.25, projection: null });
      }, [onAuthorizationChange]);
      return <div data-testid="research-run-authorization-stub" />;
    },
  };
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
  launchReservedQuestionMock.mockReset();
  navigateMock.mockReset();
  recordSpawnMock.mockReset();
});

function renderChase(props: {
  spawnContext: string;
  parentInvestigationId: string;
  reservedChildId?: string | null;
  reservedQuestionId?: string | null;
}) {
  return render(
    <MemoryRouter>
      <ChaseThread {...props} />
    </MemoryRouter>,
  );
}

describe("ChaseThread — reserved-id reuse (M2)", () => {
  it("launches INTO the reserved escalation id when present (no orphan)", async () => {
    launchReservedQuestionMock.mockResolvedValue({
      investigation_id: "inv-reserved",
      status: "in_progress",
      start_event_id: "e1",
    });
    renderChase({
      spawnContext: "margins compress at scale",
      parentInvestigationId: "inv-parent",
      reservedChildId: "inv-reserved",
      reservedQuestionId: "q-reserved",
    });
    // No launch on mount.
    expect(launchReservedQuestionMock).not.toHaveBeenCalled();

    const recursiveApproval = screen.getByText(/Approve this recursive ceiling/)
      .closest("label")
      ?.querySelector("input") as HTMLInputElement;
    fireEvent.click(recursiveApproval);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "Where do revised margins come from?" },
    });
    expect(recursiveApproval.checked).toBe(false);
    fireEvent.click(recursiveApproval);
    fireEvent.click(screen.getByText("Follow this"));
    await waitFor(() => expect(launchReservedQuestionMock).toHaveBeenCalledTimes(1));
    const [parent, questionId, arg] = launchReservedQuestionMock.mock.calls[0];
    expect(parent).toBe("inv-parent");
    expect(questionId).toBe("q-reserved");
    expect(arg).not.toHaveProperty("investigation_id");
    expect(arg.approved_run_ceiling_usd).toBe(1.25);
    expect(arg.approved_chase_ceiling_usd).toBe(2);
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
    expect(arg.approved_run_ceiling_usd).toBe(1.25);
  });
});

describe("ChaseThread — no auto-spawn (M2)", () => {
  it("launches nothing until the explicit gesture", () => {
    renderChase({
      spawnContext: "a passage",
      parentInvestigationId: "inv-parent",
      reservedChildId: "inv-reserved",
      reservedQuestionId: "q-reserved",
    });
    expect(launchReservedQuestionMock).not.toHaveBeenCalled();
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
