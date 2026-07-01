import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";

import type { StarterPanel } from "./PanelHost";

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

afterEach(() => {
  cleanup();
  panelHostMock.mockClear();
  Object.values(apiMocks).forEach((mock) => mock.mockReset());
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
