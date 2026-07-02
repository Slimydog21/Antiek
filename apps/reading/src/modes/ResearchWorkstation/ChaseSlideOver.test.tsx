/**
 * ChaseSlideOver.test.tsx — the floating chase panel contract (D11).
 *
 * The dedicated chase-tree mode remains operator-discretion polish, so this
 * pins the shipped surface that currently satisfies chase reachability: the
 * panel must not auto-launch, must let the operator refine the question, and
 * must spawn a child linked to the parent while preserving the original
 * highlighted passage as context.
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
vi.mock("../../hooks/useInvestigation", () => ({
  useInvestigation: (id: string) => ({
    id,
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
vi.mock("../../shared/delight", () => ({
  CelebrateBurst: () => null,
  useCelebrate: () => ({ celebrating: false, celebrate: vi.fn() }),
}));

import ChaseSlideOver from "./ChaseSlideOver";
import { useWorkspace } from "../../workspace/WorkspaceStore";

afterEach(() => {
  cleanup();
  startInvestigationMock.mockReset();
  navigateMock.mockReset();
  recordSpawnMock.mockReset();
  useWorkspace.getState().reset();
});

function renderPanel(props: {
  spawnContext: string;
  parentInvestigationId: string;
}) {
  return render(
    <MemoryRouter>
      <ChaseSlideOver {...props} />
    </MemoryRouter>,
  );
}

describe("ChaseSlideOver — floating chase panel contract", () => {
  it("does not launch on mount, then spawns a child with the refined question and original passage context", async () => {
    startInvestigationMock.mockResolvedValue({
      investigation_id: " inv-child ",
      status: "in_progress",
      start_event_id: "e1",
    });

    renderPanel({
      spawnContext: "the original highlighted passage",
      parentInvestigationId: "inv-parent",
    });

    expect(startInvestigationMock).not.toHaveBeenCalled();
    expect(screen.getAllByText(/the original highlighted passage/i)).toHaveLength(2);

    const question = screen.getByRole("textbox");
    fireEvent.change(question, {
      target: { value: "What would prove this highlighted claim wrong?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Spawn investigation/i }));

    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(1));
    expect(startInvestigationMock).toHaveBeenCalledWith({
      question: "What would prove this highlighted claim wrong?",
      context: "the original highlighted passage",
      parent_investigation_id: "inv-parent",
      spawn_context: "the original highlighted passage",
    });
    expect(recordSpawnMock).toHaveBeenCalledWith("inv-child", "inv-parent");
    expect(await screen.findByText("inv-child")).toBeTruthy();
  });

  it("encodes the spawned child id before opening it in the main research view", async () => {
    startInvestigationMock.mockResolvedValue({
      investigation_id: " inv dirty/child ",
      status: "in_progress",
      start_event_id: "e1",
    });

    renderPanel({
      spawnContext: "the original highlighted passage",
      parentInvestigationId: "inv-parent",
    });

    fireEvent.click(screen.getByRole("button", { name: /Spawn investigation/i }));
    await screen.findByText("inv dirty/child");
    fireEvent.click(screen.getByRole("button", { name: /open in main view/i }));

    expect(navigateMock).toHaveBeenCalledWith("/inv/inv%20dirty%2Fchild");
  });

  it("surfaces malformed child investigation ids instead of recording a spawn", async () => {
    startInvestigationMock.mockResolvedValue({
      investigation_id: " ",
      status: "in_progress",
      start_event_id: "e1",
    });

    renderPanel({
      spawnContext: "the original highlighted passage",
      parentInvestigationId: "inv-parent",
    });

    fireEvent.click(screen.getByRole("button", { name: /Spawn investigation/i }));

    expect(await screen.findByText(/investigation_id must be a non-empty string/i)).toBeTruthy();
    expect(recordSpawnMock).not.toHaveBeenCalled();
    expect(screen.queryByText("open in main view →")).toBeNull();
  });
});
