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
  listBooksMock,
  listInvestigationsMock,
  openDocumentMock,
} = vi.hoisted(() => ({
  listBooksMock: vi.fn(),
  listInvestigationsMock: vi.fn<
    () => Promise<{ count: number; investigations: InvestigationSummary[] }>
  >(),
  openDocumentMock: vi.fn(),
}));

vi.mock("../api/books", async (orig) => {
  const actual = await orig<typeof import("../api/books")>();
  return { ...actual, listBooks: listBooksMock };
});

vi.mock("../lib/api", async (orig) => {
  const actual = await orig<typeof import("../lib/api")>();
  return { ...actual, listInvestigations: listInvestigationsMock };
});

vi.mock("../lib/openDocument", async (orig) => ({
  ...(await orig<typeof import("../lib/openDocument")>()),
  useOpenDocument: () => openDocumentMock,
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
  listBooksMock.mockReset();
  listInvestigationsMock.mockReset();
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

  it("floats investigations on Cmd/Ctrl-click and keeps normal click as route navigation", async () => {
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
});
