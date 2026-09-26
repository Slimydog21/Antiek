/**
 * Diligence.test.tsx — the diligence flag affordances + the queue rail
 * (autonomous-diligence SPR-01), over three surfaces (the DRW Canvas block,
 * DistillView's open questions, the artifact receipt window) and the rail
 * itself:
 *
 *   - each surface's affordance POSTs EXACTLY ONE flag with the node's id
 *     (kind + refs, optional note) and the flag ENTERS THE RAIL as queued —
 *     the rail refetches on the diligence-changed signal, same tree;
 *   - the request body carries REFS ONLY — never the node's text (the
 *     withheld-text door, asserted on the body);
 *   - the rail renders all four statuses honestly (queued / spawned →
 *     linked investigation / done / dismissed), and a spawned flag links
 *     its investigation (stateful store mock, real component code);
 *   - a queued row's dismiss action transitions it (server round-trip).
 *
 * The island surface's flag proof lives beside the island harness
 * (Reading/island/flagFromIsland.test.tsx) — the withheld-source assertion
 * included.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactElement } from "react";

import type { DiligenceFlag } from "../../api/diligence";
import type { DistilledNode } from "../../lib/api";

const { getDistillationMock, apiFetchMock } = vi.hoisted(() => ({
  getDistillationMock: vi.fn(),
  apiFetchMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    getDistillation: getDistillationMock,
    apiFetch: (i: unknown, init?: unknown) => apiFetchMock(i, init),
  };
});

import DistillView from "./DistillView";
import DiligenceRail from "./DiligenceRail";
import BlockCard from "../DeepResearchWorkspace/Canvas/BlockCard";
import ResearchArtifactReceipt from "../../components/windows/ResearchArtifactReceipt";

// ── A tiny stateful diligence server (the transport mock with a memory) ───

interface DiligenceServer {
  flags: DiligenceFlag[];
  posts: Record<string, unknown>[];
}

function seedServer(rows: DiligenceFlag[] = []): DiligenceServer {
  const server: DiligenceServer = { flags: [...rows], posts: [] };
  apiFetchMock.mockImplementation(async (input: unknown, init?: { method?: string; body?: string }) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;

    if (url.endsWith("/diligence/flags") && method === "POST") {
      server.posts.push(parsedBody);
      const existing = server.flags.find(
        (f) =>
          f.kind === parsedBody.kind &&
          f.object_ref === parsedBody.object_ref &&
          f.status !== "dismissed",
      );
      if (existing) return jsonResponse(existing, 200);
      const row: DiligenceFlag = {
        flag_id: `dfl-${server.flags.length + 1}`,
        kind: parsedBody.kind,
        object_ref: parsedBody.object_ref,
        note: parsedBody.note ?? null,
        source_investigation_id: parsedBody.source_investigation_id ?? null,
        source_document_id: parsedBody.source_document_id ?? null,
        status: "queued",
        spawned_investigation_id: null,
        created_at: "2026-09-25T12:00:00Z",
        updated_at: "2026-09-25T12:00:00Z",
      };
      server.flags.push(row);
      return jsonResponse(row, 201);
    }
    if (url.endsWith("/diligence/queue") && method === "GET") {
      return jsonResponse({ flags: server.flags.map((f) => ({ ...f })), count: server.flags.length });
    }
    if (url.includes("/dismiss") && method === "POST") {
      const id = url.split("/flags/")[1]?.split("/dismiss")[0];
      const row = server.flags.find((f) => f.flag_id === id);
      if (!row) return jsonResponse({ detail: "diligence_flag_not_found" }, 404);
      row.status = "dismissed";
      return jsonResponse(row, 200);
    }
    return jsonResponse({ text: "reply" });
  });
  return server;
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function flagRow(over: Partial<DiligenceFlag> = {}): DiligenceFlag {
  return {
    flag_id: "dfl-1",
    kind: "open_question",
    object_ref: "q-1",
    note: null,
    source_investigation_id: "inv-1",
    source_document_id: null,
    status: "queued",
    spawned_investigation_id: null,
    created_at: "2026-09-25T12:00:00Z",
    updated_at: "2026-09-25T12:00:00Z",
    ...over,
  };
}

function node(node_id: string, kind: "insight" | "question", text: string): DistilledNode {
  return {
    node_id,
    kind,
    text,
    confidence: null,
    source_document_id: "doc-1",
    refinement_count: 0,
    escalated: false,
    reserved_child_investigation_id: null,
  };
}

function renderWithRouter(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

beforeEach(() => {
  apiFetchMock.mockReset();
  getDistillationMock.mockReset();
});

afterEach(() => {
  cleanup();
});

// ── Proof 3 (surfaces): one flag POST, refs only, the rail shows queued ───

describe("the flag affordances (Canvas block, DistillView, artifact receipt)", () => {
  it("Canvas block: one click + optional note POSTs exactly one flag with the node's id — and the rail enters it as queued", async () => {
    const server = seedServer();
    renderWithRouter(
      <>
        <BlockCard node={node("q-1", "question", "What is the moat?")} sourceInvestigationId="inv-1" />
        <DiligenceRail />
      </>,
    );
    // The rail starts empty (honest).
    await screen.findByText(/Nothing flagged yet/);

    fireEvent.click(screen.getByRole("button", { name: "flag for diligence" }));
    fireEvent.change(screen.getByLabelText(/note for the diligence flag/i), {
      target: { value: "worth a pass" },
    });
    fireEvent.click(screen.getByRole("button", { name: "flag" }));

    await waitFor(() => expect(server.posts).toHaveLength(1));
    const body = server.posts[0];
    expect(body.kind).toBe("open_question");
    expect(body.object_ref).toBe("q-1");
    expect(body.note).toBe("worth a pass");
    expect(body.source_investigation_id).toBe("inv-1");
    expect(body.source_document_id).toBe("doc-1");
    // REFS ONLY — the node's text never crosses into the request.
    expect(JSON.stringify(body)).not.toContain("What is the moat?");

    // The calm confirmation, and the rail enters the flag as queued.
    await screen.findByText(/flagged — in your diligence queue/);
    await waitFor(() =>
      expect(document.querySelector('[data-diligence-row="queued"]')).toBeTruthy(),
    );
    expect(document.querySelector("[data-diligence-rail]")!.textContent).toContain("worth a pass");
  });

  it("DistillView: an open question flags with the node id and NO note when the operator gives none", async () => {
    const server = seedServer();
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [],
      questions: [node("q-7", "question", "Where does pricing power come from?")],
    });
    renderWithRouter(
      <>
        <DistillView investigationId="inv-1" />
        <DiligenceRail />
      </>,
    );
    await screen.findByText("Where does pricing power come from?");

    fireEvent.click(screen.getByRole("button", { name: "flag for diligence" }));
    // No note — Enter submits the optional-note composer empty.
    fireEvent.keyDown(screen.getByLabelText(/note for the diligence flag/i), { key: "Enter" });

    await waitFor(() => expect(server.posts).toHaveLength(1));
    expect(server.posts[0].object_ref).toBe("q-7");
    expect(server.posts[0].kind).toBe("open_question");
    expect(server.posts[0].note).toBeNull();
    expect(JSON.stringify(server.posts[0])).not.toContain("pricing power");
    await waitFor(() =>
      expect(document.querySelector('[data-diligence-row="queued"]')).toBeTruthy(),
    );
  });

  it("artifact receipt window: its open questions carry the same affordance (one POST, the node id)", async () => {
    const server = seedServer();
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-9",
      insights: [],
      questions: [node("q-9", "question", "What remains unverified?")],
    });
    renderWithRouter(
      <ResearchArtifactReceipt
        investigationId="inv-9"
        artifactPath="/tmp/inv-9.html"
        twinNotesPath={null}
      />,
    );
    await screen.findByText(/What remains unverified/);

    fireEvent.click(screen.getByRole("button", { name: "flag for diligence" }));
    fireEvent.click(screen.getByRole("button", { name: "flag" }));

    await waitFor(() => expect(server.posts).toHaveLength(1));
    expect(server.posts[0].object_ref).toBe("q-9");
    expect(server.posts[0].source_investigation_id).toBe("inv-9");
    expect(JSON.stringify(server.posts[0])).not.toContain("unverified");
  });
});

// ── Proof 4: the rail renders all four statuses honestly ──────────────────

describe("the queue rail", () => {
  it("renders queued / spawned (linked) / done / dismissed honestly — and a spawned flag links its investigation", async () => {
    seedServer([
      flagRow({ flag_id: "dfl-q", note: "the queued one", status: "queued" }),
      flagRow({
        flag_id: "dfl-s",
        kind: "insight",
        note: "the spawned one",
        status: "spawned",
        spawned_investigation_id: "inv-spawned-1",
      }),
      flagRow({ flag_id: "dfl-d", kind: "concept", note: "the done one", status: "done" }),
      flagRow({ flag_id: "dfl-x", note: "the dismissed one", status: "dismissed" }),
    ]);
    renderWithRouter(<DiligenceRail />);

    await waitFor(() =>
      expect(document.querySelectorAll("[data-diligence-row]")).toHaveLength(4),
    );
    expect(document.querySelector('[data-diligence-row="queued"]')).toBeTruthy();
    expect(document.querySelector('[data-diligence-row="done"]')).toBeTruthy();
    expect(document.querySelector('[data-diligence-row="dismissed"]')).toBeTruthy();
    // A spawned flag LINKS its investigation.
    const link = document.querySelector("[data-diligence-spawned-link]")!;
    expect(link.getAttribute("href")).toBe("/inv/inv-spawned-1");
    // Refs stay refs: no raw object ref is ever a label.
    expect(document.querySelector("[data-diligence-rail]")!.textContent).not.toContain("q-1");
  });

  it("a queued row's dismiss transitions it (server round-trip, rail refetches)", async () => {
    const server = seedServer([flagRow({ flag_id: "dfl-q", note: "change of mind" })]);
    renderWithRouter(<DiligenceRail />);
    await waitFor(() =>
      expect(document.querySelector('[data-diligence-row="queued"]')).toBeTruthy(),
    );

    fireEvent.click(screen.getByRole("button", { name: "dismiss" }));
    await waitFor(() =>
      expect(document.querySelector('[data-diligence-row="dismissed"]')).toBeTruthy(),
    );
    expect(server.flags[0].status).toBe("dismissed");
    expect(document.querySelector('[data-diligence-row="queued"]')).toBeNull();
  });
});
