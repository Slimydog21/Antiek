/**
 * DistillView.test.tsx — insights & open questions as first-class objects
 * (SPR-03 M2) + escalation seam + honest no-key (M4).
 *
 * Pins the gates:
 *   - a completed research shows two sections, INSIGHTS + OPEN QUESTIONS,
 *     sourced from the graph (GET /research/{id}/distill), not re-derived (M2);
 *   - an escalated open question is marked "this needs more research" and is
 *     NOT launched here (M4); the chase hand-off (SPR-04) is a separate gesture;
 *   - an empty distillation (the no-key / nothing-distilled case) shows the
 *     honest no-result state, never canned insights (M4);
 *   - challenging an insight drives the backend living-note path; a 503 shows
 *     the no-key state.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { DistilledNode } from "../../lib/api";

const { getDistillationMock, challengeNoteMock } = vi.hoisted(() => ({
  getDistillationMock: vi.fn(),
  challengeNoteMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, getDistillation: getDistillationMock, challengeNote: challengeNoteMock };
});

import DistillView from "./DistillView";
import { ApiError } from "../../lib/api";
import { WERNER_EXPERIENCE_EVENT } from "../../werner";

// Reset mocks in afterEach (after cleanup), not beforeEach — see the note in
// NotesPanel.test.tsx: a reset between a prior test's caught-rejection
// microtask and the next render can surface an already-handled rejection as a
// spurious cross-test error under vitest.
afterEach(() => {
  cleanup();
  getDistillationMock.mockReset();
  challengeNoteMock.mockReset();
});

describe("DistillView — living-TV product beats", () => {
  it("emits deep_research_complete when a finished distill has product", async () => {
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [insight("i1", "GPUs gate scale.")],
      questions: [],
    });
    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (d?.experience) seen.push(d.experience);
    };
    window.addEventListener(WERNER_EXPERIENCE_EVENT, onExp);
    render(<DistillView investigationId="inv-1" running={false} />);
    await waitFor(() => expect(seen).toContain("deep_research_complete"));
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, onExp);
  });

  it("emits deep_research_start when chasing an open question", async () => {
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [],
      questions: [question("q1", "What is the moat?")],
    });
    const onChase = vi.fn();
    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (d?.experience) seen.push(d.experience);
    };
    window.addEventListener(WERNER_EXPERIENCE_EVENT, onExp);
    render(
      <DistillView investigationId="inv-1" running={false} onChase={onChase} />,
    );
    await waitFor(() => expect(screen.getByText("chase this")).toBeTruthy());
    fireEvent.click(screen.getByText("chase this"));
    expect(onChase).toHaveBeenCalled();
    expect(seen).toContain("deep_research_start");
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, onExp);
  });
});

function insight(node_id: string, text: string, extra: Partial<DistilledNode> = {}): DistilledNode {
  return { node_id, kind: "insight", text, confidence: "high", source_document_id: "doc-1", refinement_count: 0, escalated: false, reserved_child_investigation_id: null, ...extra };
}
function question(node_id: string, text: string, extra: Partial<DistilledNode> = {}): DistilledNode {
  return { node_id, kind: "question", text, confidence: null, source_document_id: "doc-1", refinement_count: 0, escalated: false, reserved_child_investigation_id: null, ...extra };
}

describe("DistillView — first-class insights + questions (M2)", () => {
  it("renders both sections from the graph result", async () => {
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [insight("i1", "GPUs gate scale.")],
      questions: [question("q1", "What is the moat?")],
    });
    render(<DistillView investigationId="inv-1" />);
    await waitFor(() => expect(screen.getByText("GPUs gate scale.")).toBeTruthy());
    expect(screen.getByText("Insights")).toBeTruthy();
    expect(screen.getByText("Open questions")).toBeTruthy();
    expect(screen.getByText("What is the moat?")).toBeTruthy();
    expect(screen.getByText("Filed findings")).toBeTruthy();
    expect(screen.getByText("Unresolved threads")).toBeTruthy();
    expect(screen.getByLabelText("1 insight").textContent).toBe("01");
    expect(screen.getByLabelText("1 open question").textContent).toBe("01");
    // grounding shown in human terms, never a raw id label.
    expect(screen.getByText("grounded in a source")).toBeTruthy();
    expect(screen.queryByText("doc-1")).toBeNull();
  });
});

describe("DistillView — escalation seam, reserve-not-launch (M4)", () => {
  it("marks an escalated question 'this needs more research' and launches nothing", async () => {
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [],
      questions: [question("q1", "Source for margins?", { escalated: true, reserved_child_investigation_id: "inv-reserved" })],
    });
    const onChase = vi.fn();
    render(<DistillView investigationId="inv-1" onChase={onChase} />);
    await waitFor(() => expect(screen.getByText("Source for margins?")).toBeTruthy());
    expect(screen.getByText("this needs more research")).toBeTruthy();
    // Nothing is launched here — the chase hand-off only fires on the gesture.
    expect(onChase).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("chase this"));
    expect(onChase).toHaveBeenCalledTimes(1);
  });
});

describe("DistillView — honest no-result (M4)", () => {
  it("shows the no-result state on an empty distillation, no canned content", async () => {
    getDistillationMock.mockResolvedValue({ investigation_id: "inv-1", insights: [], questions: [] });
    render(<DistillView investigationId="inv-1" running={false} />);
    await waitFor(() =>
      expect(screen.getByText(/distilled no insights or open questions/)).toBeTruthy(),
    );
    expect(document.querySelector(".distillation-empty__image")?.getAttribute("aria-hidden")).toBe("true");
  });

  it("shows the failure surface when the fetch fails", async () => {
    getDistillationMock.mockImplementation(async () => {
      throw new ApiError("boom", 500, "server error");
    });
    render(<DistillView investigationId="inv-1" />);
    await waitFor(() => expect(screen.getByText(/Couldn.t load the insights/)).toBeTruthy());
  });
});

describe("DistillView — challenge a completed-research insight (M3 + M4)", () => {
  it("a resolved challenge changes the note and refetches the graph", async () => {
    getDistillationMock
      .mockResolvedValueOnce({ investigation_id: "inv-1", insights: [insight("i1", "Acme is small.")], questions: [] })
      .mockResolvedValueOnce({ investigation_id: "inv-1", insights: [insight("i1", "Acme is mid-sized.", { refinement_count: 1 })], questions: [] });
    challengeNoteMock.mockResolvedValue({ node_id: "i1", applied: true, superseded: false, new_text: "Acme is mid-sized.", escalated: false, reserved_child_investigation_id: null });
    render(<DistillView investigationId="inv-1" />);
    await waitFor(() => expect(screen.getByText("Acme is small.")).toBeTruthy());
    fireEvent.click(screen.getByText("challenge this"));
    await waitFor(() => expect(screen.getByText("Acme is mid-sized.")).toBeTruthy());
    expect(challengeNoteMock).toHaveBeenCalledWith("i1", { investigation_id: "inv-1" });
    expect(getDistillationMock).toHaveBeenCalledTimes(2); // refetched after the change
  });

  it("a 503 challenge shows the no-key state", async () => {
    getDistillationMock.mockResolvedValue({ investigation_id: "inv-1", insights: [insight("i1", "A claim.")], questions: [] });
    challengeNoteMock.mockImplementation(async () => {
      throw new ApiError("no provider", 503, "no model");
    });
    render(<DistillView investigationId="inv-1" />);
    await waitFor(() => expect(screen.getByText("A claim.")).toBeTruthy());
    fireEvent.click(screen.getByText("challenge this"));
    await waitFor(() => expect(screen.getByText(/model provider isn/)).toBeTruthy());
  });
});
