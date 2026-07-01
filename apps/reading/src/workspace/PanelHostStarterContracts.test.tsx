import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";

import type { StarterPanel } from "./PanelHost";
import { useWorkspace } from "./WorkspaceStore";

const panelHostMock = vi.hoisted(() =>
  vi.fn(({ children }: { starters?: StarterPanel[]; children: ReactNode }) => (
    <div data-testid="panel-host">{children}</div>
  )),
);

const apiMocks = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  listWatchForLater: vi.fn(),
  launchParkedQuestion: vi.fn(),
  attachBlock: vi.fn(),
  createSection: vi.fn(),
  exportDeliverable: vi.fn(),
  getDeliverable: vi.fn(),
  reorderBlock: vi.fn(),
  updateSectionProse: vi.fn(),
}));

vi.mock("./PanelHost", () => ({
  PanelHost: panelHostMock,
}));

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: apiMocks.apiFetch,
  listWatchForLater: apiMocks.listWatchForLater,
  launchParkedQuestion: apiMocks.launchParkedQuestion,
  attachBlock: apiMocks.attachBlock,
  createSection: apiMocks.createSection,
  exportDeliverable: apiMocks.exportDeliverable,
  getDeliverable: apiMocks.getDeliverable,
  reorderBlock: apiMocks.reorderBlock,
  updateSectionProse: apiMocks.updateSectionProse,
}));

vi.mock("../lib/analytics", () => ({
  track: vi.fn(),
}));

vi.mock("../components/TrajectoryReplay", () => ({
  default: () => <div data-testid="trajectory-replay" />,
}));

import Replay from "../modes/Replay";
import CreationStudio from "../modes/CreationStudio";
import InterviewMode from "../modes/Interview";
import BrainstormStation from "../modes/BrainstormStation";

class MockWebSocket {
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((message: { data: string }) => void) | null = null;

  constructor() {
    setTimeout(() => this.onopen?.(), 0);
  }

  close() {
    this.onclose?.();
  }
}

function latestStarters(): StarterPanel[] {
  const calls = panelHostMock.mock.calls;
  const props = calls[calls.length - 1]?.[0] as { starters?: StarterPanel[] } | undefined;
  return props?.starters ?? [];
}

function mountAt(path: string, element: ReactNode, route: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={route} element={element} />
      </Routes>
    </MemoryRouter>,
  );
}

function CreationStudioWithJump() {
  const navigate = useNavigate();
  return (
    <>
      <button type="button" onClick={() => navigate("/create/del-2")}>
        Open second deliverable
      </button>
      <CreationStudio />
    </>
  );
}

function deliverableDetail(deliverableId: string, title: string) {
  return {
    deliverable_id: deliverableId,
    title,
    deliverable_kind: "research_memo",
    status: "draft",
    investigation_root_id: null,
    sections: [],
  };
}

function deferredDeliverable(deliverableId: string, title: string) {
  let resolve!: (value: ReturnType<typeof deliverableDetail>) => void;
  const promise = new Promise<ReturnType<typeof deliverableDetail>>((done) => {
    resolve = done;
  });
  return {
    promise,
    resolve: () => resolve(deliverableDetail(deliverableId, title)),
  };
}

afterEach(() => {
  cleanup();
  panelHostMock.mockClear();
  Object.values(apiMocks).forEach((mock) => mock.mockReset());
  useWorkspace.getState().reset();
  vi.unstubAllGlobals();
});

describe("route PanelHost starter contracts", () => {
  it("Replay opens the step list dock for the active investigation", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    apiMocks.apiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ events: [] }),
    });

    mountAt("/replay/inv-42", <Replay />, "/replay/:investigationId");

    await waitFor(() => expect(panelHostMock).toHaveBeenCalled());
    expect(latestStarters()).toEqual([
      {
        kind: "ReplayStepList",
        mode: "docked-left",
        title: "Steps",
        id: "replay:inv-42:steps",
        props: { investigationId: "inv-42" },
      },
    ]);
  });

  it("CreationStudio opens deliverables and block-palette side panels", () => {
    mountAt("/create", <CreationStudio />, "/create/:deliverableId?");

    expect(latestStarters()).toEqual([
      {
        kind: "DeliverableSidebar",
        mode: "docked-left",
        title: "Deliverables",
        id: "create:deliverable-sidebar",
      },
      {
        kind: "BlockPalette",
        mode: "docked-right",
        title: "Block palette",
        id: "create:block-palette",
      },
    ]);
  });

  it("CreationStudio opens a preview workspace panel for the active deliverable", async () => {
    apiMocks.getDeliverable.mockResolvedValue({
      deliverable_id: "del-1",
      title: "Research memo",
      deliverable_kind: "research_memo",
      status: "draft",
      investigation_root_id: null,
      sections: [],
    });

    mountAt("/create/del-1", <CreationStudio />, "/create/:deliverableId?");

    await waitFor(() => expect(apiMocks.getDeliverable).toHaveBeenCalled());
    expect(latestStarters()).toEqual([
      {
        kind: "DeliverableSidebar",
        mode: "docked-left",
        title: "Deliverables",
        id: "create:deliverable-sidebar",
      },
      {
        kind: "BlockPalette",
        mode: "docked-right",
        title: "Block palette",
        id: "create:block-palette",
      },
    ]);
    await waitFor(() =>
      expect(useWorkspace.getState().panels["create:del-1:preview"]).toMatchObject({
        kind: "DeliverablePreview",
        mode: "docked-bottom",
        title: "Preview",
        props: { deliverableId: "del-1" },
      }),
    );
  });

  it("CreationStudio swaps the preview panel when the active deliverable changes", async () => {
    apiMocks.getDeliverable.mockResolvedValue(
      deliverableDetail("del-1", "Research memo"),
    );

    mountAt(
      "/create/del-1",
      <CreationStudioWithJump />,
      "/create/:deliverableId?",
    );

    await waitFor(() =>
      expect(useWorkspace.getState().panels["create:del-1:preview"]).toBeTruthy(),
    );

    await userEvent.click(
      screen.getByRole("button", { name: "Open second deliverable" }),
    );

    await waitFor(() =>
      expect(useWorkspace.getState().panels["create:del-2:preview"]).toMatchObject({
        kind: "DeliverablePreview",
        props: { deliverableId: "del-2" },
      }),
    );
    expect(useWorkspace.getState().panels["create:del-1:preview"]).toBeUndefined();
    expect(latestStarters()).toEqual([
      {
        kind: "DeliverableSidebar",
        mode: "docked-left",
        title: "Deliverables",
        id: "create:deliverable-sidebar",
      },
      {
        kind: "BlockPalette",
        mode: "docked-right",
        title: "Block palette",
        id: "create:block-palette",
      },
    ]);
  });

  it("CreationStudio keeps the active canvas detail when route fetches resolve out of order", async () => {
    const stale = deferredDeliverable("del-1", "Stale memo");
    const fresh = deferredDeliverable("del-2", "Fresh memo");
    apiMocks.getDeliverable
      .mockReturnValueOnce(stale.promise)
      .mockReturnValueOnce(fresh.promise);

    mountAt(
      "/create/del-1",
      <CreationStudioWithJump />,
      "/create/:deliverableId?",
    );

    await waitFor(() =>
      expect(apiMocks.getDeliverable).toHaveBeenCalledWith("del-1"),
    );

    await userEvent.click(
      screen.getByRole("button", { name: "Open second deliverable" }),
    );

    await waitFor(() =>
      expect(apiMocks.getDeliverable).toHaveBeenCalledWith("del-2"),
    );
    fresh.resolve();
    expect(await screen.findByRole("heading", { name: "Fresh memo" })).toBeTruthy();

    stale.resolve();
    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Stale memo" })).toBeNull(),
    );
  });

  it("CreationStudio clears the previous canvas detail while a new deliverable loads", async () => {
    const fresh = deferredDeliverable("del-2", "Fresh memo");
    apiMocks.getDeliverable
      .mockResolvedValueOnce(deliverableDetail("del-1", "Old memo"))
      .mockReturnValueOnce(fresh.promise);

    mountAt(
      "/create/del-1",
      <CreationStudioWithJump />,
      "/create/:deliverableId?",
    );

    expect(await screen.findByRole("heading", { name: "Old memo" })).toBeTruthy();

    await userEvent.click(
      screen.getByRole("button", { name: "Open second deliverable" }),
    );

    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Old memo" })).toBeNull(),
    );
    fresh.resolve();
    expect(await screen.findByRole("heading", { name: "Fresh memo" })).toBeTruthy();
  });

  it("CreationStudio keeps the current canvas detail when a same-deliverable refresh fails", async () => {
    apiMocks.getDeliverable
      .mockResolvedValueOnce(deliverableDetail("del-1", "Old memo"))
      .mockRejectedValueOnce(new Error("offline"));
    apiMocks.createSection.mockResolvedValue({});

    mountAt("/create/del-1", <CreationStudio />, "/create/:deliverableId?");

    expect(await screen.findByRole("heading", { name: "Old memo" })).toBeTruthy();

    await userEvent.type(
      screen.getByPlaceholderText(/New section title/),
      "New section",
    );
    await userEvent.click(screen.getByRole("button", { name: "Add section" }));

    await waitFor(() => expect(apiMocks.createSection).toHaveBeenCalled());
    expect(screen.getByRole("heading", { name: "Old memo" })).toBeTruthy();
    expect(screen.queryByText("Deliverable not found.")).toBeNull();
  });

  it("Interview opens recording, transcript, and notes panels with the route id", async () => {
    apiMocks.apiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        interview_id: "int-7",
        project_id: "project-1",
        project_title: "Biography interview",
        topic_description: null,
        framing: null,
        must_cover: [],
        status: "active",
        consent_recorded: true,
        transcript: [],
      }),
    });

    mountAt("/interview/int-7", <InterviewMode />, "/interview/:interviewId");

    await waitFor(() => expect(panelHostMock).toHaveBeenCalled());
    expect(latestStarters()).toEqual([
      {
        kind: "InterviewRecording",
        mode: "docked-left",
        title: "Recording",
        id: "interview:int-7:recording",
        props: { interviewId: "int-7", consentRecorded: true },
      },
      {
        kind: "InterviewTranscript",
        mode: "docked-right",
        title: "Transcript",
        id: "interview:int-7:transcript",
        props: { interviewId: "int-7" },
      },
      {
        kind: "InterviewNotes",
        mode: "docked-bottom",
        title: "Notes",
        id: "interview:int-7:notes",
        props: { interviewId: "int-7" },
      },
    ]);
  });

  it("Brainstorm opens watch-list and thought-partner side panels", async () => {
    apiMocks.listWatchForLater.mockResolvedValue({ questions: [] });

    mountAt("/brainstorm", <BrainstormStation />, "/brainstorm");

    await waitFor(() => expect(panelHostMock).toHaveBeenCalled());
    expect(latestStarters()).toEqual([
      {
        kind: "BrainstormWatchList",
        mode: "docked-left",
        title: "Watch for later",
        id: "brainstorm:watchlist",
      },
      {
        kind: "BrainstormThoughtPartner",
        mode: "docked-right",
        title: "Thought partner",
        id: "brainstorm:thought-partner",
      },
    ]);
  });
});
