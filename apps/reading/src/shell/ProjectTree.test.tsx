import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { BookSummary } from "../api/books";
import type { InvestigationSummary } from "../lib/api";
import { usePinned } from "../components/navigation/pinnedStore";
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

afterEach(() => cleanup());

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
    expect(navigateMock).toHaveBeenCalledWith("/documents/doc-live-seeded");
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
      expect(screen.getByText(/Could not load recent items: backend unavailable/)).toBeTruthy(),
    );
    expect(screen.queryByText("No recent items yet.")).toBeNull();
    expect(screen.queryByText("Loading recent items...")).toBeNull();
    expectNoFabricatedIds(container);
  });
});
