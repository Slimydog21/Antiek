import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { BookSummary } from "../api/books";
import { ApiError, type InvestigationSummary } from "../lib/api";
import { usePinned } from "../components/navigation/pinnedStore";
import { useWorkspace } from "../workspace/WorkspaceStore";
import ProjectTree from "./ProjectTree";

const { listBooksMock, listInvestigationsMock, navigateMock } = vi.hoisted(() => ({
  listBooksMock: vi.fn(),
  listInvestigationsMock: vi.fn<
    () => Promise<{ count: number; investigations: InvestigationSummary[] }>
  >(),
  navigateMock: vi.fn(),
}));

vi.mock("../api/books", async (orig) => {
  const actual = await orig<typeof import("../api/books")>();
  return { ...actual, listBooks: listBooksMock };
});

vi.mock("../lib/api", async (orig) => {
  const actual = await orig<typeof import("../lib/api")>();
  return { ...actual, listInvestigations: listInvestigationsMock };
});

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

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

beforeEach(() => {
  listBooksMock.mockReset();
  listInvestigationsMock.mockReset();
  navigateMock.mockReset();
  usePinned.getState().clear();
  listBooksMock.mockResolvedValue({ books: [], count: 0 });
  listInvestigationsMock.mockResolvedValue({ count: 0, investigations: [] });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function expectNoFabricatedIds(container: HTMLElement) {
  for (const id of fabricatedIds) {
    expect(container.innerHTML).not.toContain(id);
  }
}

function renderTree(workflow: "research" | "read" | "write" | "speak") {
  return render(
    <MemoryRouter>
      <ProjectTree workflow={workflow} />
    </MemoryRouter>,
  );
}

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
    expect(navigateMock).toHaveBeenCalledWith("/inv/inv-live-seeded");
    expectNoFabricatedIds(container);
  });

  it("renders live read documents and routes with the seeded id", async () => {
    listBooksMock.mockResolvedValue({ books: [liveBook], count: 1 });

    const { container } = renderTree("read");

    const row = await screen.findByText("Live seeded document");
    expect(listBooksMock).toHaveBeenCalledWith("all");
    expect(row.closest("[data-node-id]")?.getAttribute("data-node-id")).toBe(
      "doc-live-seeded",
    );
    fireEvent.click(row);
    expect(navigateMock).toHaveBeenCalledWith("/wrestle/doc-live-seeded");
    expectNoFabricatedIds(container);
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
      expect(screen.getByText("Couldn't load your recent items.")).toBeTruthy(),
    );
    expect(container.textContent).not.toContain("backend unavailable");
    expect(screen.queryByText("No recent items yet.")).toBeNull();
    expect(screen.queryByText("Loading recent items...")).toBeNull();
    expectNoFabricatedIds(container);
  });
});

describe("ProjectTree recent-items failure (F-07 class)", () => {
  // The raw error string used to render after "Could not load recent items:".
  const RAW = /\b[1-5]\d\d\b|HTTP|\/books|\/investigations|GET|Failed to fetch/;

  it("a 503 loading documents shows the humanised title and no status or path", async () => {
    listBooksMock.mockRejectedValue(new ApiError("GET /books?filter=all failed: HTTP 503", 503, "down"));
    const { container } = renderTree("read");
    await waitFor(() => expect(screen.getByText("Couldn't load your recent items.")).toBeTruthy());
    expect(container.textContent).toContain("Antiek is busy or restarting.");
    expect(container.textContent).not.toMatch(RAW);
  });

  it("a network TypeError shows the offline description, not 'Failed to fetch'", async () => {
    listBooksMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const { container } = renderTree("read");
    await waitFor(() => expect(screen.getByText("Couldn't load your recent items.")).toBeTruthy());
    expect(container.textContent).toContain("can't be reached");
    expect(container.textContent).not.toMatch(RAW);
  });

  it("a research-list failure never shows the raw message either", async () => {
    listInvestigationsMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const { container } = renderTree("research");
    await waitFor(() => expect(screen.getByText("Couldn't load your recent items.")).toBeTruthy());
    expect(container.textContent).not.toMatch(RAW);
  });
});

describe("ProjectTree modifier-click (F-02)", () => {
  // F-02: ⌘/Ctrl-click used to open a floating panel with { id } props that
  // Trajectory / Notebook / PdfViewer do not accept (Trajectory threw). It
  // must navigate in a new tab to the row's route and never open a panel.
  const liveNotebookless = { count: 1, investigations: [liveInvestigation] };

  function spies() {
    const openPanel = vi.fn();
    useWorkspace.setState({ open: openPanel } as Partial<ReturnType<typeof useWorkspace.getState>>);
    const windowOpen = vi.spyOn(window, "open").mockReturnValue(null);
    return { openPanel, windowOpen };
  }

  it.each([
    ["metaKey", { metaKey: true }],
    ["ctrlKey", { ctrlKey: true }],
  ])("%s on an investigation row opens /inv/<id> in a new tab and never a panel", async (_k, mods) => {
    listInvestigationsMock.mockResolvedValue(liveNotebookless);
    const { openPanel, windowOpen } = spies();
    renderTree("research");

    fireEvent.click(await screen.findByText("Live seeded investigation"), mods);

    expect(openPanel).not.toHaveBeenCalled();
    expect(windowOpen).toHaveBeenCalledTimes(1);
    expect(windowOpen).toHaveBeenCalledWith("/inv/inv-live-seeded", "_blank", "noopener");
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("metaKey on a document row opens the same route a plain click navigates to", async () => {
    listBooksMock.mockResolvedValue({ books: [liveBook], count: 1 });
    const { openPanel, windowOpen } = spies();
    renderTree("read");

    fireEvent.click(await screen.findByText("Live seeded document"), { metaKey: true });

    expect(windowOpen).toHaveBeenCalledWith("/wrestle/doc-live-seeded", "_blank", "noopener");
    expect(openPanel).not.toHaveBeenCalled();
  });

  it("a plain click keeps navigating in place and opens nothing", async () => {
    listInvestigationsMock.mockResolvedValue(liveNotebookless);
    const { openPanel, windowOpen } = spies();
    renderTree("research");

    fireEvent.click(await screen.findByText("Live seeded investigation"));

    expect(navigateMock).toHaveBeenCalledWith("/inv/inv-live-seeded");
    expect(windowOpen).not.toHaveBeenCalled();
    expect(openPanel).not.toHaveBeenCalled();
  });
});
