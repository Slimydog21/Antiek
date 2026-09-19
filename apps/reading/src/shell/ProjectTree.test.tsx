import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { BookSummary } from "../api/books";
import type { InvestigationSummary } from "../lib/api";
import { usePinned } from "../components/navigation/pinnedStore";
import { useWorkspace } from "../workspace/WorkspaceStore";
import { EMPTY_SNAPSHOT } from "../workspace/panel.types";
import ProjectTree from "./ProjectTree";

const { authHarness, createPrivateWriteMock, listBooksMock, listInvestigationsMock, listPrivateWriteMock, navigateMock } = vi.hoisted(() => ({
  authHarness: { generation: 1 },
  createPrivateWriteMock: vi.fn(),
  listBooksMock: vi.fn(),
  listInvestigationsMock: vi.fn<
    () => Promise<{ count: number; investigations: InvestigationSummary[] }>
  >(),
  listPrivateWriteMock: vi.fn(),
  navigateMock: vi.fn(),
}));

vi.mock("../api/books", async (orig) => {
  const actual = await orig<typeof import("../api/books")>();
  return { ...actual, listBooks: listBooksMock };
});

vi.mock("../lib/api", async (orig) => {
  const actual = await orig<typeof import("../lib/api")>();
  return {
    ...actual,
    listInvestigations: listInvestigationsMock,
    listPrivateWriteDocuments: listPrivateWriteMock,
    createNativePrivateWrite: createPrivateWriteMock,
  };
});

vi.mock("../lib/auth", () => ({
  useAuth: () => ({ sessionGeneration: authHarness.generation }),
}));

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
  createPrivateWriteMock.mockReset();
  authHarness.generation = 1;
  listInvestigationsMock.mockReset();
  listPrivateWriteMock.mockReset();
  navigateMock.mockReset();
  usePinned.getState().clear();
  useWorkspace.setState({ ...EMPTY_SNAPSHOT });
  listBooksMock.mockResolvedValue({ books: [], count: 0 });
  listInvestigationsMock.mockResolvedValue({ count: 0, investigations: [] });
  listPrivateWriteMock.mockResolvedValue({ documents: [], next_after_document_id: null });
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
    expect(navigateMock).toHaveBeenCalledWith("/wrestle/doc-live-seeded");
    expectNoFabricatedIds(container);
  });

  it("Cmd-click opens canonical hosted HTML panel with the same document id", async () => {
    listBooksMock.mockResolvedValue({ books: [liveBook], count: 1 });
    renderTree("read");
    fireEvent.click(await screen.findByText("Live seeded document"), { metaKey: true });
    const panel = Object.values(useWorkspace.getState().panels)[0];
    expect(panel.kind).toBe("HostedDocument");
    expect(panel.props).toEqual({ id: "doc-live-seeded" });
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("renders an honest empty state for a Write account without manuscripts", async () => {
    const { container } = renderTree("write");

    expect(await screen.findByText("No recent items yet.")).toBeTruthy();
    expectNoFabricatedIds(container);
  });

  it("discovers private manuscripts and opens one stable authority-only revision desk", async () => {
    listPrivateWriteMock.mockResolvedValue({
      documents: [{
        write_document_id: "ivwd-owner-1", project_id: "project-owner-1",
        title: "Evidence manuscript", revision: 4, html_sha256: "a".repeat(64),
        visibility: "private", updated_at: "2026-07-16 10:00:00",
        origin_kind: "ai_composition",
      }],
      next_after_document_id: null,
    });
    renderTree("write");

    const row = await screen.findByText("Evidence manuscript");
    fireEvent.click(row); fireEvent.click(row);
    const panels = Object.values(useWorkspace.getState().panels);
    expect(panels).toHaveLength(1);
    expect(panels[0]).toMatchObject({
      id: "PrivateWrite:project-owner-1:ivwd-owner-1", kind: "PrivateWrite",
      props: { projectId: "project-owner-1", writeDocumentId: "ivwd-owner-1" },
    });
    expect(Object.keys(panels[0].props)).toEqual(["projectId", "writeDocumentId"]);
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("creates one owner-native manuscript and launches its stable desk", async () => {
    createPrivateWriteMock.mockResolvedValue({
      event_id: `ivwn-create-${"3".repeat(25)}`, write_document_id: `ivwd-${"2".repeat(32)}`,
      project_id: `ivwp-${"1".repeat(32)}`, title: "My analysis", revision: 1,
      html_sha256: "b".repeat(64), visibility: "private",
      origin_kind: "owner_native", replayed: false,
    });
    renderTree("write");
    fireEvent.click(await screen.findByRole("button", { name: /New manuscript/ }));
    const input = screen.getByLabelText("Title");
    fireEvent.change(input, { target: { value: "My analysis" } });
    const create = screen.getByRole("button", { name: "Create manuscript" });
    fireEvent.click(create); fireEvent.click(create);
    await waitFor(() => expect(createPrivateWriteMock).toHaveBeenCalledTimes(1));
    expect(createPrivateWriteMock).toHaveBeenCalledWith(
      "My analysis",
      expect.any(String),
      expect.any(AbortSignal),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const panels = Object.values(useWorkspace.getState().panels);
    expect(panels).toHaveLength(1);
    expect(panels[0]).toMatchObject({
      id: `PrivateWrite:ivwp-${"1".repeat(32)}:ivwd-${"2".repeat(32)}`, kind: "PrivateWrite",
      props: { projectId: `ivwp-${"1".repeat(32)}`, writeDocumentId: `ivwd-${"2".repeat(32)}` },
    });
  });

  it("retains the title on create failure and Escape returns focus", async () => {
    createPrivateWriteMock.mockRejectedValue(new Error("authority unavailable"));
    renderTree("write");
    const invoker = await screen.findByRole("button", { name: /New manuscript/ });
    fireEvent.click(invoker);
    const input = screen.getByLabelText("Title") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Retained title" } });
    fireEvent.click(screen.getByRole("button", { name: "Create manuscript" }));
    await screen.findByRole("alert");
    expect(input.value).toBe("Retained title");
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(globalThis.document.activeElement).toBe(invoker);
  });

  it("walks private manuscript pages and rejects source-bearing collection items", async () => {
    const first = {
      write_document_id: "ivwd-1", project_id: "project-1", title: "First",
      revision: 1, html_sha256: "1".repeat(64), visibility: "private",
      updated_at: "2026-07-16 10:00:00",
      origin_kind: "ai_composition",
    };
    listPrivateWriteMock
      .mockResolvedValueOnce({ documents: [first], next_after_document_id: "ivwd-1" })
      .mockResolvedValueOnce({
        documents: [{ ...first, write_document_id: "ivwd-2", title: "Second", html: "LEAK" }],
        next_after_document_id: null,
      });
    const { container } = renderTree("write");
    await waitFor(() => expect(screen.getByText(/collection authority is inconsistent/)).toBeTruthy());
    expect(container.textContent).not.toContain("LEAK");
    expect(listPrivateWriteMock).toHaveBeenNthCalledWith(2, expect.any(AbortSignal), "ivwd-1", 100);
  });

  it("aborts the old private collection and suppresses its bytes after session change", async () => {
    let resolveOld!: (value: unknown) => void;
    const oldPage = new Promise((resolve) => { resolveOld = resolve; });
    listPrivateWriteMock
      .mockImplementationOnce(() => oldPage)
      .mockResolvedValueOnce({ documents: [], next_after_document_id: null });
    const rendered = renderTree("write");
    await waitFor(() => expect(listPrivateWriteMock).toHaveBeenCalledTimes(1));
    const oldSignal = listPrivateWriteMock.mock.calls[0][0] as AbortSignal;

    authHarness.generation = 2;
    rendered.rerender(<MemoryRouter><ProjectTree workflow="write" /></MemoryRouter>);
    await waitFor(() => expect(listPrivateWriteMock).toHaveBeenCalledTimes(2));
    expect(oldSignal.aborted).toBe(true);
    resolveOld({
      documents: [{
        write_document_id: "ivwd-stale", project_id: "project-stale", title: "STALE SECRET",
        revision: 1, html_sha256: "a".repeat(64), visibility: "private",
        updated_at: "2026-07-16 10:00:00",
        origin_kind: "ai_composition",
      }],
      next_after_document_id: null,
    });
    await waitFor(() => expect(screen.getByText("No recent items yet.")).toBeTruthy());
    expect(rendered.container.textContent).not.toContain("STALE SECRET");
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
