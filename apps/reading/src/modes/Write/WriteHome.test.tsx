import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";

import { emitTraceIntent } from "./Editor/traceIntent";
import type { TraceTarget } from "./writeApi";

/**
 * WriteHome.test — the re-homed Write door (Product Depth SPR-07 M1+M4).
 *
 * Load-bearing claims, mechanically checked:
 *  - the door opens on a real "start a piece" surface — NOT the legacy
 *    "Select or create a deliverable to begin." dead-end;
 *  - a citation chip's trace-to-source intent routes to the source reader
 *    when the source is servable, and falls back honestly (no dead page)
 *    when it isn't (§9.0 gated / unreachable).
 */

const {
  listDeliverablesMock, getDeliverableMock, getTraceTargetMock, listInvestigationsMock,
  startInvestigationMock, createDeliverableMock, promoteContextMock, generateSectionMock,
  getSectionBlocksMock,
} = vi.hoisted(() => ({
  listDeliverablesMock: vi.fn(),
  getDeliverableMock: vi.fn(),
  getTraceTargetMock: vi.fn(),
  listInvestigationsMock: vi.fn(),
  startInvestigationMock: vi.fn(),
  createDeliverableMock: vi.fn(),
  promoteContextMock: vi.fn(),
  generateSectionMock: vi.fn(),
  getSectionBlocksMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  listDeliverables: listDeliverablesMock,
  getDeliverable: getDeliverableMock,
  createDeliverable: createDeliverableMock,
  listInvestigations: listInvestigationsMock,
  startInvestigation: startInvestigationMock,
}));

vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  getTraceTarget: getTraceTargetMock,
  promoteContext: promoteContextMock,
  generateSection: generateSectionMock,
  getSectionBlocks: getSectionBlocksMock,
}));

import WriteHome, { readerPageFromTraceSectionPath } from "./WriteHome";

function ReaderProbe() {
  const { documentId } = useParams<{ documentId: string }>();
  const location = useLocation();
  return (
    <div>
      READER {documentId} {location.search}
    </div>
  );
}

function ResearchProbe() {
  const { investigationId } = useParams<{ investigationId: string }>();
  return <div>RESEARCH {investigationId}</div>;
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function RouteSwitchProbe() {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate("/write/dlv-fresh")}>
      open fresh piece
    </button>
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

beforeEach(() => {
  listDeliverablesMock.mockReset().mockResolvedValue({ count: 0, deliverables: [] });
  getDeliverableMock.mockReset().mockResolvedValue(null);
  getTraceTargetMock.mockReset();
  listInvestigationsMock.mockReset().mockResolvedValue({ count: 0, investigations: [] });
  startInvestigationMock.mockReset().mockResolvedValue({
    investigation_id: "inv-spawned", status: "in_progress", start_event_id: "ev-1",
  });
  createDeliverableMock.mockReset().mockResolvedValue({
    deliverable_id: "dlv-new", title: "Memo", deliverable_kind: "general_essay",
    investigation_root_id: "inv-spawned", status: "draft",
    created_at: null, updated_at: null, section_count: 0,
  });
  promoteContextMock.mockReset().mockResolvedValue({
    deliverable_id: "dlv-open",
    section_id: "sec-context",
    block_ids: ["oblk-context"],
  });
  getSectionBlocksMock.mockReset().mockResolvedValue([]);
  generateSectionMock.mockReset().mockResolvedValue({
    status: "gap",
    section_id: "sec-context",
    detail: "no model needed for this test",
  });
  // WriteHome now renders through GlassSurface (SPR-03 M2 landing-glass home /
  // M3 solid open-piece), which reads prefers-reduced-motion via
  // window.matchMedia. jsdom lacks it; stub the default (motion allowed → the
  // glass variant renders). Weakens nothing.
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});
afterEach(cleanup);

function mountAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <LocationProbe />
      <Routes>
        <Route path="/write" element={<WriteHome />} />
        <Route path="/write/:deliverableId" element={<WriteHome />} />
        <Route path="/read/:documentId" element={<ReaderProbe />} />
        <Route path="/inv/:investigationId" element={<ResearchProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("WriteHome — the re-homed door", () => {
  it("parses trace section paths into zero-based reader pages", () => {
    expect(readerPageFromTraceSectionPath("Page 17")).toBe(16);
    expect(readerPageFromTraceSectionPath("p. 3")).toBe(2);
    expect(readerPageFromTraceSectionPath("Timestamp 00:17")).toBeUndefined();
    expect(readerPageFromTraceSectionPath(null)).toBeUndefined();
  });

  it("the no-piece Write home is LANDING-GLASS (SPR-03 M2 occlusion contract)", async () => {
    // Audit §3 item 5: the Write home (no piece) is a landing surface, rendered
    // through GlassSurface variant="glass" so the scene shows through the margins.
    // (The open-piece branch is dense-legible-keep-opaque = variant="solid"; that
    // contract is proven in GlassSurface.test.tsx + the audit §3 row + the source.)
    // A refactor swapping the home to an opaque body / solid would re-occlude the
    // mountain on /write; this enforces the variant per-route (rigor #5).
    const { container } = mountAt("/write");
    await screen.findByPlaceholderText(/what are you writing/i);
    const surface = container.querySelector("[data-glass-surface]");
    expect(surface, "the Write home must render through GlassSurface").toBeTruthy();
    expect(surface!.getAttribute("data-glass-variant")).toBe("glass");
  });

  it("opens on a real start-a-piece surface, not the 'select a deliverable' dead-end", async () => {
    mountAt("/write");
    // The action-first door (U-04): name the piece (SPR-09 M1 then prompts the
    // research connection before the piece is created).
    expect(
      await screen.findByPlaceholderText(/what are you writing/i),
    ).toBeTruthy();
    // The legacy dead-end sentence is gone.
    expect(screen.queryByText(/select or create a deliverable/i)).toBeNull();
    // And the brainstorm on-ramp is offered as the outline-optional entry.
    expect(screen.getByText(/brainstorm from an idea/i)).toBeTruthy();
  });

  it("drops malformed listed pieces and trims the routable piece id", async () => {
    listDeliverablesMock.mockResolvedValue({
      count: 3,
      deliverables: [
        {
          deliverable_id: " dlv-valid ",
          title: "  Valid memo  ",
          deliverable_kind: "not-a-kind",
          investigation_root_id: " inv-root ",
          status: "",
          created_at: null,
          updated_at: null,
          section_count: "2",
        },
        {
          deliverable_id: "dlv-unlinked",
          title: "Unlinked memo",
          deliverable_kind: "general_essay",
          investigation_root_id: " ",
          status: "draft",
          created_at: null,
          updated_at: null,
          section_count: 0,
        },
        {
          deliverable_id: " ",
          title: "Invisible memo",
          deliverable_kind: "general_essay",
          investigation_root_id: null,
          status: "draft",
          created_at: null,
          updated_at: null,
          section_count: 1,
        },
      ],
    });

    mountAt("/write");
    const piece = await screen.findByText("Valid memo");
    expect(screen.getByText("2 sections · connected to research")).toBeTruthy();
    expect(screen.getByText("0 sections · no research connected")).toBeTruthy();
    expect(screen.queryByText("Invisible memo")).toBeNull();
    await userEvent.click(piece);
    await waitFor(() => expect(getDeliverableMock).toHaveBeenCalledWith("dlv-valid"));
  });

  it("encodes listed piece ids before opening them", async () => {
    listDeliverablesMock.mockResolvedValue({
      count: 1,
      deliverables: [
        {
          deliverable_id: "dlv dirty/valid",
          title: "Dirty routed memo",
          deliverable_kind: "general_essay",
          investigation_root_id: "inv-root",
          status: "draft",
          created_at: null,
          updated_at: null,
          section_count: 1,
        },
      ],
    });

    mountAt("/write");
    await userEvent.click(await screen.findByText("Dirty routed memo"));

    expect(screen.getByTestId("location").textContent).toBe(
      "/write/dlv%20dirty%2Fvalid",
    );
  });

  it("sanitizes open-piece detail before rendering sections", async () => {
    getDeliverableMock.mockResolvedValue({
      deliverable_id: " dlv-open ",
      title: " ",
      deliverable_kind: "not-a-kind",
      investigation_root_id: " ",
      status: "",
      sections: [
        {
          section_id: " sec-1 ",
          deliverable_id: " dlv-open ",
          parent_section_id: " ",
          section_index: "0",
          title: " ",
          prose_text: null,
          prose_provenance: [],
          block_count: "2",
        },
        {
          section_id: "",
          deliverable_id: "dlv-open",
          parent_section_id: null,
          section_index: 1,
          title: "Invisible section",
          prose_text: null,
          prose_provenance: null,
          block_count: 0,
        },
      ],
    });

    mountAt("/write/dlv-open");

    expect(await screen.findByText("Untitled piece")).toBeTruthy();
    expect(await screen.findByText("(untitled section)")).toBeTruthy();
    expect(screen.queryByText("Invisible section")).toBeNull();
    expect(getSectionBlocksMock).toHaveBeenCalledWith("sec-1");
  });

  it("keeps stale open-piece responses from overwriting the active routed piece", async () => {
    const stale = deferred<unknown>();
    const fresh = deferred<unknown>();
    getDeliverableMock.mockReturnValueOnce(stale.promise).mockReturnValueOnce(fresh.promise);

    render(
      <MemoryRouter initialEntries={["/write/dlv-stale"]}>
        <RouteSwitchProbe />
        <Routes>
          <Route path="/write/:deliverableId" element={<WriteHome />} />
        </Routes>
      </MemoryRouter>,
    );

    await userEvent.click(screen.getByRole("button", { name: /open fresh piece/i }));
    await act(async () => {
      fresh.resolve({
        deliverable_id: "dlv-fresh",
        title: "Fresh memo",
        deliverable_kind: "general_essay",
        investigation_root_id: null,
        status: "draft",
        sections: [],
      });
    });

    expect(await screen.findByText("Fresh memo")).toBeTruthy();

    await act(async () => {
      stale.resolve({
        deliverable_id: "dlv-stale",
        title: "Stale memo",
        deliverable_kind: "general_essay",
        investigation_root_id: null,
        status: "draft",
        sections: [],
      });
    });

    expect(screen.getByText("Fresh memo")).toBeTruthy();
    expect(screen.queryByText("Stale memo")).toBeNull();
  });

  it("does not emit brainstorm blocks from the no-piece sentinel section", async () => {
    mountAt("/write");
    await userEvent.click(await screen.findByText(/brainstorm from an idea/i));
    expect(
      await screen.findByText(/Start a piece first to land blocks on a real section/i),
    ).toBeTruthy();
    const emit = screen.getByRole("button", { name: /emit lego blocks/i });
    expect((emit as HTMLButtonElement).disabled).toBe(true);
  });

  it("M1 — 'none' auto-spawns a research folder and creates the piece linked to it", async () => {
    mountAt("/write");
    // Naming the piece reveals the connect-to-research step (M1).
    const title = await screen.findByPlaceholderText(/what are you writing/i);
    await userEvent.type(title, "A margins memo");
    // Choose "none" → auto-spawn + link.
    await userEvent.click(await screen.findByText(/start without a project/i));
    await waitFor(() => expect(createDeliverableMock).toHaveBeenCalled());
    // The piece is created WITH the spawned investigation_root_id (the link is
    // set at creation — verified by the create call carrying it, not a UI claim).
    expect(createDeliverableMock).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "A margins memo",
        investigation_root_id: "inv-spawned",
      }),
    );
  });

  it("encodes a newly created piece id before opening it", async () => {
    createDeliverableMock.mockResolvedValue({
      deliverable_id: "dlv dirty/new",
      title: "Memo",
      deliverable_kind: "general_essay",
      investigation_root_id: "inv-spawned",
      status: "draft",
      created_at: null,
      updated_at: null,
      section_count: 0,
    });

    mountAt("/write");
    await userEvent.type(
      await screen.findByPlaceholderText(/what are you writing/i),
      "A margins memo",
    );
    await userEvent.click(await screen.findByText(/start without a project/i));
    await waitFor(() => expect(createDeliverableMock).toHaveBeenCalled());

    expect(screen.getByTestId("location").textContent).toBe(
      "/write/dlv%20dirty%2Fnew",
    );
  });

  it("promotes open-piece context into the current deliverable, not a stray draft", async () => {
    getDeliverableMock.mockResolvedValue({
      deliverable_id: "dlv-open",
      title: "Open piece",
      deliverable_kind: "general_essay",
      investigation_root_id: "inv-root",
      status: "draft",
      created_at: null,
      updated_at: null,
      sections: [],
    });

    mountAt("/write/dlv-open");
    await screen.findByText("Open piece");
    await userEvent.click(screen.getByRole("button", { name: /brainstorm a section/i }));

    const dropZone = screen
      .getByText(/Drag lego blocks here from the repository/i)
      .closest("div");
    expect(dropZone).toBeTruthy();
    fireEvent.drop(dropZone!, {
      dataTransfer: {
        types: ["application/x-antiek-block"],
        getData: (type: string) =>
          type === "application/x-antiek-block"
            ? JSON.stringify({
                from: "palette",
                block_id: "node-context",
                block_kind: "insight",
                label: "a context block",
              })
            : "",
      },
    });
    await userEvent.type(
      screen.getByPlaceholderText(/state the writing objective/i),
      "turn this into the next section",
    );
    await userEvent.click(screen.getByRole("button", { name: /promote to outline/i }));

    await waitFor(() => expect(promoteContextMock).toHaveBeenCalled());
    expect(promoteContextMock).toHaveBeenCalledWith(
      expect.objectContaining({
        deliverable_id: "dlv-open",
        objective: "turn this into the next section",
        blocks: [
          expect.objectContaining({
            provenance_kind: "graph_node",
            node_id: "node-context",
          }),
        ],
      }),
    );
  });

  it("opens the linked backing research folder from an active Write piece", async () => {
    getDeliverableMock.mockResolvedValue({
      deliverable_id: "dlv-open",
      title: "Open piece",
      deliverable_kind: "general_essay",
      investigation_root_id: " inv-root ",
      status: "draft",
      created_at: null,
      updated_at: null,
      sections: [],
    });

    mountAt("/write/dlv-open");

    expect(await screen.findByText("Open piece")).toBeTruthy();
    expect(screen.getByTestId("active-connection").textContent).toContain(
      "Connected to research",
    );
    await userEvent.click(screen.getByRole("button", { name: /open research/i }));

    expect(await screen.findByText("RESEARCH inv-root")).toBeTruthy();
  });

  it("does not offer a research jump when the open piece is unlinked", async () => {
    getDeliverableMock.mockResolvedValue({
      deliverable_id: "dlv-open",
      title: "Open piece",
      deliverable_kind: "general_essay",
      investigation_root_id: " ",
      status: "draft",
      created_at: null,
      updated_at: null,
      sections: [],
    });

    mountAt("/write/dlv-open");

    expect(await screen.findByText("No research connected")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /open research/i })).toBeNull();
  });

  it("routes a servable trace-to-source to the source reader", async () => {
    const target: TraceTarget = {
      kind: "document",
      full_text_allowed: true,
      document_id: "doc-1",
      document_title: "Source Book",
      chunk_ids: ["c1"],
      primary_chunk_index: 0,
      primary_section_path: "Page 1",
      servability_status: "servable",
      detail: null,
    };
    getTraceTargetMock.mockResolvedValue(target);
    mountAt("/write");
    await screen.findByPlaceholderText(/what are you writing/i);

    emitTraceIntent({
      sectionId: "sec-1",
      outlineBlockId: "oblk-1",
      nodeId: "node-1",
      provenanceKind: "graph_node",
    });
    // The honest trip: a servable source opens the one Reader and preserves the
    // chunk locator, so the Reader can resolve chunk → region without a
    // fabricated block id.
    await waitFor(() => expect(screen.getByText("READER doc-1 ?page=0&chunk=c1")).toBeTruthy());
  });

  it("does not navigate when an allowed trace lacks a usable document id", async () => {
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    getTraceTargetMock.mockResolvedValue({
      kind: "document",
      full_text_allowed: true,
      document_id: " ",
      document_title: "  Source Book  ",
      chunk_ids: [" c1 ", "", 99],
      primary_chunk_index: "0",
      primary_section_path: "Page 1",
      servability_status: "servable",
      detail: " ",
    });
    mountAt("/write");
    await screen.findByPlaceholderText(/what are you writing/i);

    emitTraceIntent({
      sectionId: "sec-1",
      outlineBlockId: "oblk-malformed",
      nodeId: "node-1",
      provenanceKind: "graph_node",
    });

    await waitFor(() => expect(alertSpy).toHaveBeenCalled());
    expect(screen.queryByText(/READER/)).toBeNull();
    alertSpy.mockRestore();
  });

  it("falls back honestly (no dead page) when the source is gated/unreachable", async () => {
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    const gated: TraceTarget = {
      kind: "document",
      full_text_allowed: false, // the no-leak bit
      document_id: "doc-gated",
      document_title: "Gated Book",
      chunk_ids: [],
      primary_chunk_index: null,
      primary_section_path: null,
      servability_status: "restricted_pending_opt_in",
      detail: "this source is gated",
    };
    getTraceTargetMock.mockResolvedValue(gated);
    mountAt("/write");
    await screen.findByPlaceholderText(/what are you writing/i);

    emitTraceIntent({
      sectionId: "sec-1",
      outlineBlockId: "oblk-gated",
      nodeId: "node-g",
      provenanceKind: "graph_node",
    });
    await waitFor(() => expect(alertSpy).toHaveBeenCalled());
    // It did NOT navigate to a dead reader page.
    expect(screen.queryByText(/READER/)).toBeNull();
    alertSpy.mockRestore();
  });
});
