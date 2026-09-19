import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

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
  listDeliverablesMock, getTraceTargetMock, listInvestigationsMock,
  startInvestigationMock, createDeliverableMock, createFromInvestigationMock,
} = vi.hoisted(() => ({
  listDeliverablesMock: vi.fn(),
  getTraceTargetMock: vi.fn(),
  listInvestigationsMock: vi.fn(),
  startInvestigationMock: vi.fn(),
  createDeliverableMock: vi.fn(),
  createFromInvestigationMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  listDeliverables: listDeliverablesMock,
  getDeliverable: vi.fn().mockResolvedValue(null),
  createDeliverable: createDeliverableMock,
  listInvestigations: listInvestigationsMock,
  startInvestigation: startInvestigationMock,
}));

vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  getTraceTarget: getTraceTargetMock,
  createDeliverableFromInvestigation: createFromInvestigationMock,
}));

import { ApiError } from "../../lib/api";
import WriteHome from "./WriteHome";

beforeEach(() => {
  listDeliverablesMock.mockReset().mockResolvedValue({ count: 0, deliverables: [] });
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
  createFromInvestigationMock.mockReset().mockRejectedValue(
    new ApiError("POST /write/deliverables/from-investigation failed: HTTP 404", 404, "no_synthesis"),
  );
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
      <Routes>
        <Route path="/write" element={<WriteHome />} />
        <Route path="/write/:deliverableId" element={<WriteHome />} />
        <Route path="/read/:documentId" element={<div>READER</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("WriteHome — the re-homed door", () => {
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

  it("routes a servable trace-to-source to the source reader", async () => {
    const target: TraceTarget = {
      kind: "document",
      full_text_allowed: true,
      document_id: "doc-1",
      document_title: "Source Book",
      chunk_ids: ["c1"],
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
    // The honest trip: a servable source opens the reader.
    await waitFor(() => expect(screen.getByText("READER")).toBeTruthy());
  });

  it("falls back honestly (no dead page) when the source is gated/unreachable", async () => {
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    const gated: TraceTarget = {
      kind: "document",
      full_text_allowed: false, // the no-leak bit
      document_id: "doc-gated",
      document_title: "Gated Book",
      chunk_ids: [],
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
    expect(screen.queryByText("READER")).toBeNull();
    alertSpy.mockRestore();
  });

  it("outline→Write: connects via from-investigation when synthesis exists", async () => {
    listInvestigationsMock.mockResolvedValue({
      count: 1,
      investigations: [{
        investigation_id: "inv-notebook",
        question: "What compounds?",
        status: "completed",
        spawned_by_daemon: false,
      }],
    });
    createFromInvestigationMock.mockResolvedValue({
      deliverable_id: "dlv-seeded",
      section_id: "sec-1",
      block_count: 3,
      dangling_count: 0,
      source_node_count: 3,
      insufficient_evidence: false,
      synthesis_id: "syn-1",
      synthesis_status: "passed",
      synthesis_recommendation: null,
    });
    mountAt("/write?investigation=inv-notebook");
    const title = await screen.findByPlaceholderText(/what are you writing/i);
    await userEvent.type(title, "Compounding memo");
    expect(await screen.findByTestId("connect-research-preferred")).toBeTruthy();
    await userEvent.click(await screen.findByText(/What compounds/i));
    await waitFor(() => expect(createFromInvestigationMock).toHaveBeenCalled());
    expect(createFromInvestigationMock).toHaveBeenCalledWith(
      expect.objectContaining({
        investigation_id: "inv-notebook",
        title: "Compounding memo",
      }),
    );
    expect(createDeliverableMock).not.toHaveBeenCalled();
  });

  it("notebook→Write continuity: prefills title and shows banner", async () => {
    listInvestigationsMock.mockResolvedValue({
      count: 1,
      investigations: [{
        investigation_id: "inv-notebook",
        question: "What is the moat?",
        status: "completed",
        spawned_by_daemon: false,
      }],
    });
    mountAt("/write?investigation=inv-notebook&title=Moat%20memo");
    const title = await screen.findByPlaceholderText(/what are you writing/i);
    expect((title as HTMLInputElement).value).toBe("Moat memo");
    expect(screen.getByTestId("write-from-notebook-banner")).toBeTruthy();
    expect(await screen.findByTestId("connect-research-preferred")).toBeTruthy();
  });
});
