import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
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

const { listDeliverablesMock, getTraceTargetMock } = vi.hoisted(() => ({
  listDeliverablesMock: vi.fn(),
  getTraceTargetMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  listDeliverables: listDeliverablesMock,
  getDeliverable: vi.fn().mockResolvedValue(null),
  createDeliverable: vi.fn(),
}));

vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  getTraceTarget: getTraceTargetMock,
}));

import WriteHome from "./WriteHome";

beforeEach(() => {
  listDeliverablesMock.mockReset().mockResolvedValue({ count: 0, deliverables: [] });
  getTraceTargetMock.mockReset();
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
  it("opens on a real start-a-piece surface, not the 'select a deliverable' dead-end", async () => {
    mountAt("/write");
    // The action-first door (U-04): start writing.
    expect(await screen.findByRole("button", { name: /start writing/i })).toBeTruthy();
    // The legacy dead-end sentence is gone.
    expect(screen.queryByText(/select or create a deliverable/i)).toBeNull();
    // And the brainstorm on-ramp is offered as the outline-optional entry.
    expect(screen.getByText(/brainstorm from an idea/i)).toBeTruthy();
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
    await screen.findByRole("button", { name: /start writing/i });

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
    await screen.findByRole("button", { name: /start writing/i });

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
});
