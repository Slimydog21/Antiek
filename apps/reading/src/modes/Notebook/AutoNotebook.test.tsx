/**
 * AutoNotebook.test.tsx — SPR-06 M1, the auto-notebook surface
 * (PROPOSED — sign-off pending).
 *
 * Pins:
 *   - the "proposed (sign-off pending)" banner renders on the auto view;
 *   - the dynamic outline + sections render from REAL graph content
 *     (getDistillation), and FLIP when the graph changes (the load-bearing
 *     graph-change re-derive — distillation [insight A, question B] → add
 *     insight C);
 *   - an empty graph shows an HONEST empty state, never fabricated content
 *     (rigor #1);
 *   - the §9.0 no-leak: a withheld source's BODY never renders (the synthesis
 *     section is rendered by MasterMdViewer, which owns the servable guard).
 *
 * Mocks at the hook + api boundary so jsdom needs no socket (the ChaseThread /
 * Reading test pattern). useInvestigation is stubbed with a controllable
 * InvestigationState; getDistillation + getChunk are vi.fn()s.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { Event } from "../../generated/types";
import type { DistilledNode } from "../../lib/api";

const { getDistillationMock, getChunkMock } = vi.hoisted(() => ({
  getDistillationMock: vi.fn(),
  getChunkMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    getDistillation: getDistillationMock,
    getChunk: getChunkMock,
  };
});

// useInvestigation reads the live WS stream; stub at the hook boundary. We
// drive `events` (synthesis parsed from them) + status + question via a module
// mutable so a test can change the graph and re-render.
const investigationStub: {
  status: "loading" | "in_progress" | "completed" | "failed" | "not_found";
  question: string | null;
  events: Event[];
} = { status: "completed", question: "What is the moat?", events: [] };

vi.mock("../../hooks/useInvestigation", () => ({
  useInvestigation: (id: string | null) => ({
    id: id ?? "",
    status: investigationStub.status,
    question: investigationStub.question,
    events: investigationStub.events,
    terminalPayload: null,
    costTotal: 0,
    completedAt: null,
    streamStatus: "open",
    reconnects: 0,
  }),
}));

// MasterMdViewer measures DOM geometry (ResizeObserver); jsdom lacks it.
class FakeResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
beforeEach(() => {
  (globalThis as unknown as { ResizeObserver: typeof FakeResizeObserver }).ResizeObserver =
    FakeResizeObserver;
});

import AutoNotebook from "./AutoNotebook";

afterEach(() => {
  cleanup();
  getDistillationMock.mockReset();
  getChunkMock.mockReset();
  investigationStub.status = "completed";
  investigationStub.question = "What is the moat?";
  investigationStub.events = [];
});

function insight(node_id: string, text: string): DistilledNode {
  return {
    node_id,
    kind: "insight",
    text,
    confidence: "high",
    source_document_id: "doc-1",
    refinement_count: 0,
    escalated: false,
    reserved_child_investigation_id: null,
  };
}
function question(node_id: string, text: string): DistilledNode {
  return {
    node_id,
    kind: "question",
    text,
    confidence: null,
    source_document_id: null,
    refinement_count: 0,
    escalated: false,
    reserved_child_investigation_id: null,
  };
}

function renderAt(investigationId: string) {
  return render(
    <MemoryRouter initialEntries={[`/notebook/auto/${investigationId}`]}>
      <Routes>
        <Route
          path="/notebook/auto/:investigationId"
          element={<AutoNotebook />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AutoNotebook — the proposed banner (M1, rigor #1 honesty)", () => {
  it("renders the 'proposed — sign-off pending' banner on the auto view", async () => {
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [insight("i1", "GPUs gate scale.")],
      questions: [],
    });
    renderAt("inv-1");
    const banner = await screen.findByTestId("auto-notebook-proposed-banner");
    expect(banner).toBeTruthy();
    expect(banner.textContent).toMatch(/proposed/i);
    expect(banner.textContent).toMatch(/sign-off pending/i);
    expect(banner.textContent).toMatch(/isn.t ratified yet/i);
  });
});

describe("AutoNotebook — renders real graph content (M1)", () => {
  it("derives the outline + sections from the distillation", async () => {
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [insight("i1", "GPUs gate scale.")],
      questions: [question("q1", "Where is the moat?")],
    });
    renderAt("inv-1");
    await waitFor(() =>
      expect(screen.getByText("GPUs gate scale.")).toBeTruthy(),
    );
    expect(screen.getByText("Where is the moat?")).toBeTruthy();
    // The outline lists both sections (derived from the graph's themes).
    const outline = screen.getByTestId("auto-notebook-outline");
    expect(outline.querySelector('[data-outline-section="insights"]')).toBeTruthy();
    expect(outline.querySelector('[data-outline-section="questions"]')).toBeTruthy();
    // Title is the research question — not invented.
    expect(screen.getByText("What is the moat?")).toBeTruthy();
  });
});

describe("AutoNotebook — graph-change re-derive (M1 load-bearing)", () => {
  it("flips the rendered outline + sections when an insight is added", async () => {
    // BEFORE: distillation = [insight A, question B].
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [insight("A", "Insight A.")],
      questions: [question("B", "Question B?")],
    });
    const { rerender } = renderAt("inv-1");
    await waitFor(() => expect(screen.getByText("Insight A.")).toBeTruthy());
    expect(screen.queryByText("Insight C.")).toBeNull();

    // AFTER: the graph changes — a new event arrives (advancing the event
    // count, which the wrapper keys its distillation re-fetch on) AND the
    // distillation now returns the added insight C.
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [insight("A", "Insight A."), insight("C", "Insight C.")],
      questions: [question("B", "Question B?")],
    });
    investigationStub.events = [
      { event_id: "e1", emitted_at: "2026-05-28T00:00:00Z" } as unknown as Event,
    ];
    rerender(
      <MemoryRouter initialEntries={["/notebook/auto/inv-1"]}>
        <Routes>
          <Route
            path="/notebook/auto/:investigationId"
            element={<AutoNotebook />}
          />
        </Routes>
      </MemoryRouter>,
    );

    // The added insight now renders — the section flipped on the graph change.
    await waitFor(() => expect(screen.getByText("Insight C.")).toBeTruthy());
    expect(screen.getByText("Insight A.")).toBeTruthy();
  });
});

describe("AutoNotebook — honest empty state (M1, rigor #1)", () => {
  it("shows an honest empty state, never fabricated content", async () => {
    investigationStub.events = [];
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-empty",
      insights: [],
      questions: [],
    });
    renderAt("inv-empty");
    await waitFor(() =>
      expect(
        screen.getByText(/nothing in the graph to narrate yet/i),
      ).toBeTruthy(),
    );
    // The banner is still present (it's the auto view).
    expect(screen.getByTestId("auto-notebook-proposed-banner")).toBeTruthy();
    // No outline / fabricated sections.
    expect(screen.queryByTestId("auto-notebook-outline")).toBeNull();
  });
});

describe("AutoNotebook — §9.0 no-leak (M1)", () => {
  it("never renders a withheld source's body in the synthesis section", async () => {
    const RESTRICTED_BODY = "SECRET-RESTRICTED-BODY-DO-NOT-LEAK";
    // A completed research whose synthesis cites one chunk. The synthesis is
    // parsed from these events (synthesize.delivered + completed).
    investigationStub.status = "completed";
    investigationStub.question = "What is the moat?";
    investigationStub.events = [
      {
        event_id: "e0",
        emitted_at: "2026-05-28T00:00:00Z",
        action_type: "investigation.start_requested",
        payload: { question: "What is the moat?" },
      } as unknown as Event,
      {
        event_id: "e1",
        emitted_at: "2026-05-28T00:00:01Z",
        action_type: "synthesize.delivered",
        payload: {
          thesis_summary: "The moat is data scale.",
          thesis_components: [
            {
              claim: "Data scale compounds.",
              confidence: "high",
              supporting_chunk_ids: ["chunk-restricted"],
              supporting_path_indices: [],
            },
          ],
        },
      } as unknown as Event,
      {
        event_id: "e2",
        emitted_at: "2026-05-28T00:00:02Z",
        action_type: "investigation.completed",
        payload: { thesis_summary: "The moat is data scale." },
      } as unknown as Event,
    ];
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-restricted",
      insights: [],
      questions: [],
    });
    // §9.0: the endpoint withholds a restricted source's body — but even if a
    // body leaked into the payload, the surface must NEVER render it. We seed
    // the body to a sentinel and assert it never appears.
    getChunkMock.mockResolvedValue({
      chunk_id: "chunk-restricted",
      text: RESTRICTED_BODY,
      section_path: null,
      token_count: 0,
      document_id: "doc-restricted",
      document_title: "A restricted paper",
      source_tier: 1,
      servable: false,
      ip_holder_name: null,
    });

    renderAt("inv-restricted");
    // The synthesis section renders (the claim + the named source).
    await waitFor(() =>
      expect(screen.getByText("Data scale compounds.")).toBeTruthy(),
    );
    // The §9.0 honest withholding state shows; the BODY never does.
    await waitFor(() =>
      expect(screen.getByText(/not available to open/i)).toBeTruthy(),
    );
    expect(screen.queryByText(RESTRICTED_BODY)).toBeNull();
    expect(document.body.textContent).not.toContain(RESTRICTED_BODY);
  });
});
