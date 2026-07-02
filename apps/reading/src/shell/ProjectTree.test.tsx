import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import type { BookSummary } from "../api/books";
import type { InvestigationSummary } from "../lib/api";
import { usePinned } from "../components/navigation/pinnedStore";
import { useWorkspace } from "../workspace/WorkspaceStore";
import ProjectTree from "./ProjectTree";
import type { Workflow } from "./workflowTaxonomy";

const {
  listDeliverablesMock,
  listBooksMock,
  listInvestigationsMock,
  listPeopleMock,
  openDocumentMock,
} = vi.hoisted(() => ({
  listDeliverablesMock: vi.fn(),
  listBooksMock: vi.fn(),
  listInvestigationsMock: vi.fn<
    () => Promise<{ count: number; investigations: InvestigationSummary[] }>
  >(),
  listPeopleMock: vi.fn(),
  openDocumentMock: vi.fn(),
}));

vi.mock("../api/books", async (orig) => {
  const actual = await orig<typeof import("../api/books")>();
  return { ...actual, listBooks: listBooksMock };
});

vi.mock("../lib/api", async (orig) => {
  const actual = await orig<typeof import("../lib/api")>();
  return {
    ...actual,
    listDeliverables: listDeliverablesMock,
    listInvestigations: listInvestigationsMock,
  };
});

vi.mock("../lib/openDocument", async (orig) => ({
  ...(await orig<typeof import("../lib/openDocument")>()),
  useOpenDocument: () => openDocumentMock,
}));

vi.mock("../lib/speakApi", async (orig) => ({
  ...(await orig<typeof import("../lib/speakApi")>()),
  listPeople: listPeopleMock,
}));

const fabricatedIds = [
  "nvda-q4",
  "web-gaming-2026",
  "kalshi-liquidity",
  "kalshi-paper",
  "synth-nvda",
];

const liveInvestigation: InvestigationSummary = {
  investigation_id: "inv-live-seeded",
  question: "Live seeded investigation",
  status: "in_progress",
  started_at: null,
  completed_at: null,
  cost_usd_total: 0,
  parent_investigation_id: null,
};

const liveBook: BookSummary = {
  document_id: "doc-live-seeded",
  title: "Live seeded document",
  author: "Operator",
  servability: "public_domain",
  servable_full_text: true,
  page_count: 12,
  cover_uri: null,
  ip_holder_id: null,
  taken_down: false,
};

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function expectNoFabricatedIds(container: HTMLElement) {
  for (const id of fabricatedIds) {
    expect(container.innerHTML).not.toContain(id);
  }
}

function renderTree(workflow: Exclude<Workflow, "shared"> = "read") {
  return render(
    <MemoryRouter initialEntries={["/library"]}>
      <Routes>
        <Route
          path="*"
          element={
            <>
              <ProjectTree workflow={workflow} />
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  listDeliverablesMock.mockReset().mockResolvedValue({ count: 0, deliverables: [] });
  listBooksMock.mockReset();
  listInvestigationsMock.mockReset();
  listPeopleMock.mockReset().mockResolvedValue([]);
  openDocumentMock.mockReset();
  usePinned.getState().clear();
  useWorkspace.getState().reset();
  listBooksMock.mockResolvedValue({ books: [], count: 0 });
  listInvestigationsMock.mockResolvedValue({ count: 0, investigations: [] });
});

afterEach(cleanup);

describe("ProjectTree", () => {
  it("renders live research investigations and routes with the seeded id", async () => {
    listInvestigationsMock.mockResolvedValue({
      count: 1,
      investigations: [liveInvestigation],
    });

    const { container } = renderTree("research");

    const row = await screen.findByText("Live seeded investigation");
    expect(row.closest("[data-node-id]")?.getAttribute("data-node-id")).toBe(
      "inv-live-seeded",
    );
    fireEvent.click(row);
    expect(screen.getByTestId("location").textContent).toBe(
      "/inv/inv-live-seeded",
    );
    expectNoFabricatedIds(container);
  });

  it("keeps Read All links aligned to Library, Meta-docs, Notebooks", async () => {
    renderTree("read");

    expect(screen.getByText("Library · Meta-docs · Notebooks")).toBeTruthy();
    expect(await screen.findByRole("button", { name: /Your readings/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /All meta-docs/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /All notebooks/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /All documents/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /All sources/ })).toBeNull();
  });

  it("opens a live document through the one Reader door on normal click", async () => {
    listBooksMock.mockResolvedValue({ books: [liveBook], count: 1 });

    const { container } = renderTree("read");

    const row = await screen.findByText("Live seeded document");
    expect(listBooksMock).toHaveBeenCalledWith("all");
    expect(row.closest("[data-node-id]")?.getAttribute("data-node-id")).toBe(
      "doc-live-seeded",
    );
    fireEvent.click(row);
    expect(openDocumentMock).toHaveBeenCalledTimes(1);
    expect(openDocumentMock).toHaveBeenCalledWith("doc-live-seeded");
    expect(useWorkspace.getState().floatingIds).toEqual([]);
    expect(screen.getByTestId("location").textContent).toBe("/library");
    expectNoFabricatedIds(container);
  });

  it("opens a live document in inspect mode on Cmd/Ctrl-click", async () => {
    listBooksMock.mockResolvedValue({ books: [liveBook], count: 1 });

    renderTree("read");

    fireEvent.click(await screen.findByText("Live seeded document"), {
      metaKey: true,
    });

    expect(openDocumentMock).toHaveBeenCalledTimes(1);
    expect(openDocumentMock).toHaveBeenCalledWith("doc-live-seeded", {
      mode: "inspect",
    });
    expect(useWorkspace.getState().floatingIds).toEqual([]);
  });

  it("loads live Research investigations and opens Research home", async () => {
    const secondInvestigation: InvestigationSummary = {
      ...liveInvestigation,
      investigation_id: "inv-live-secondary",
      question: "Second live investigation",
    };
    listInvestigationsMock.mockResolvedValue({
      count: 2,
      investigations: [liveInvestigation, secondInvestigation],
    });

    renderTree("research");

    fireEvent.click(await screen.findByText("Live seeded investigation"), {
      ctrlKey: true,
    });
    const floatingId = useWorkspace.getState().floatingIds[0];
    expect(useWorkspace.getState().panels[floatingId]).toMatchObject({
      kind: "Trajectory",
      props: { id: "inv-live-seeded" },
      mode: "floating",
      title: "Live seeded investigation",
    });
    expect(screen.getByTestId("location").textContent).toBe("/library");

    fireEvent.click(screen.getByText("Second live investigation"));
    expect(screen.getByTestId("location").textContent).toBe(
      "/inv/inv-live-secondary",
    );
  });

  it("pins item-specific rows with accessible labels and moves them above Recent", async () => {
    listBooksMock.mockResolvedValue({ books: [liveBook], count: 1 });

    renderTree("read");

    await screen.findByText("Live seeded document");
    fireEvent.click(screen.getByLabelText("Pin Live seeded document"));

    expect(usePinned.getState().isPinned("document:doc-live-seeded")).toBe(true);
    expect(screen.getByLabelText("Unpin Live seeded document")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Pinned\s*1/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Recent\s*0/ })).toBeTruthy();
  });

  it("renders an honest empty state for workflows without a recents data layer", () => {
    const { container } = renderTree("write");

    expect(screen.getByText("No recent items yet.")).toBeTruthy();
    expectNoFabricatedIds(container);
  });

  it("renders a distinct error state without falling back to fabricated items", async () => {
    listInvestigationsMock.mockRejectedValue(new Error("backend unavailable"));

    const { container } = renderTree("research");

    await waitFor(() =>
      expect(
        screen.getByText(/Could not load recent items: backend unavailable/),
      ).toBeTruthy(),
    );
    expect(screen.queryByText("No recent items yet.")).toBeNull();
    expect(screen.queryByText("Loading recent items...")).toBeNull();
    expectNoFabricatedIds(container);
  });

  it("loads live Write pieces into the workflow tree and opens the Write loop", async () => {
    listDeliverablesMock.mockResolvedValue({
      count: 3,
      deliverables: [
        { deliverable_id: " dlv-live ", title: "  Live memo  " },
        { deliverable_id: " ", title: "Skipped memo" },
        { deliverable_id: "dlv-untitled", title: " " },
      ],
    });
    renderTree("write");

    expect(await screen.findByText("Live memo")).toBeTruthy();
    expect(await screen.findByText("Untitled piece")).toBeTruthy();
    expect(screen.queryByText("Skipped memo")).toBeNull();
    expect(screen.getByRole("button", { name: /Recent\s*2/ })).toBeTruthy();

    fireEvent.click(screen.getByText("Live memo"));
    await waitFor(() => {
      expect(screen.getByTestId("location").textContent).toBe("/write/dlv-live");
    });
  });

  it("opens Write pieces as floating previews on Cmd/Ctrl-click", async () => {
    listDeliverablesMock.mockResolvedValue({
      count: 1,
      deliverables: [{ deliverable_id: "dlv-preview", title: "Preview memo" }],
    });
    renderTree("write");

    fireEvent.click(await screen.findByText("Preview memo"), { metaKey: true });

    const floatingId = useWorkspace.getState().floatingIds[0];
    expect(useWorkspace.getState().panels[floatingId]).toMatchObject({
      kind: "DeliverablePreview",
      props: { deliverableId: "dlv-preview" },
      mode: "floating",
      title: "Preview memo",
    });
    expect(screen.getByTestId("location").textContent).toBe("/library");
  });

  it("loads live Speak people and opens the Speak project", async () => {
    listPeopleMock.mockResolvedValue([
      { id: " person-live ", name: "  Ada Lovelace  ", willBePublic: false, voiceCount: 2 },
      { id: "person-zero", name: "Grace Hopper", willBePublic: true, voiceCount: 0 },
      { id: " ", name: "Skipped person", willBePublic: false, voiceCount: 1 },
      { id: "person-untitled", name: " ", willBePublic: false, voiceCount: -1 },
    ]);

    renderTree("speak");

    expect(await screen.findByText("Ada Lovelace · 2 voices")).toBeTruthy();
    expect(screen.getByText("Grace Hopper · no voices yet")).toBeTruthy();
    expect(screen.getByText("Untitled remembrance · no voices yet")).toBeTruthy();
    expect(screen.queryByText(/Skipped person/)).toBeNull();
    expect(screen.getByRole("button", { name: /Recent\s*3/ })).toBeTruthy();

    fireEvent.click(screen.getByText("Ada Lovelace · 2 voices"));
    await waitFor(() => {
      expect(screen.getByTestId("location").textContent).toBe("/speak/person-live");
    });
  });

  it("routes Speak people on Cmd/Ctrl-click because no floating Speak panel exists", async () => {
    listPeopleMock.mockResolvedValue([
      { id: "person-route", name: "Route person", willBePublic: false, voiceCount: 1 },
    ]);

    renderTree("speak");

    fireEvent.click(await screen.findByText("Route person · 1 voice"), { metaKey: true });

    await waitFor(() => {
      expect(screen.getByTestId("location").textContent).toBe("/speak/person-route");
    });
    expect(useWorkspace.getState().floatingIds).toEqual([]);
  });
});
