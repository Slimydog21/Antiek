/**
 * NotesPanel.test.tsx — auto-notes + living notes (SPR-03 M1 + M3).
 *
 * Pins the gates the sprint page names:
 *   - notes appear from the event stream as the research runs (M1);
 *   - reconnect idempotency: a re-delivered note.emerged is counted once,
 *     no doubled note after a dropped socket (M1 gate);
 *   - living note: a note.refined collapses onto its note — the text changes
 *     IN PLACE, it does not duplicate, and the prior text is recoverable via
 *     "see what changed" (M3);
 *   - the challenge gesture drives the backend living-note path (POST
 *     .../challenge); a 503 (no model) shows the honest no-key state, never a
 *     fabricated change (M3 + M4).
 *
 * The deriveNotes reducer is exercised directly (it's the pure core), then the
 * component is rendered with the api mocked at the module boundary.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { Event } from "../../generated/types";
import type { InvestigationState } from "../../hooks/useInvestigation";

const { challengeNoteMock } = vi.hoisted(() => ({ challengeNoteMock: vi.fn() }));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, challengeNote: challengeNoteMock };
});

import NotesPanel, { deriveNotes } from "./NotesPanel";
import { ApiError } from "../../lib/api";

// Reset the mock in afterEach (AFTER cleanup unmounts), not beforeEach: a
// reset between a prior test's lingering caught-rejection microtask and the
// next render is what surfaces an already-handled 503 rejection as a spurious
// cross-test error under vitest.
afterEach(() => {
  cleanup();
  challengeNoteMock.mockReset();
});

let seq = 0;
function ev(actionType: string, payload: Record<string, unknown>): Event {
  seq += 1;
  return {
    event_id: `e${seq}`,
    investigation_id: "inv-test",
    action_type: actionType as Event["action_type"],
    payload: payload as unknown as Event["payload"],
    param_version: "v1",
    emitted_at: `2026-05-26T00:00:${String(seq).padStart(2, "0")}Z`,
  };
}

function state(events: Event[], overrides: Partial<InvestigationState> = {}): InvestigationState {
  return {
    id: "inv-test",
    status: "in_progress",
    question: "Q",
    events,
    terminalPayload: null,
    costTotal: 0,
    completedAt: null,
    streamStatus: "open",
    reconnects: 0,
    sourcePolicy: [],
    ...overrides,
  };
}

describe("deriveNotes — the pure reducer (M1 + M3)", () => {
  it("turns note.emerged / question.identified into rows in order", () => {
    const notes = deriveNotes([
      ev("note.emerged", { note_id: "n1", note_text: "GPUs gate scale.", confidence: "high" }),
      ev("question.identified", { question_id: "q1", question_text: "What is the moat?" }),
    ]);
    expect(notes.map((n) => [n.kind, n.text])).toEqual([
      ["insight", "GPUs gate scale."],
      ["question", "What is the moat?"],
    ]);
  });

  it("is idempotent across a reconnect — a re-delivered note is counted once", () => {
    const e = ev("note.emerged", { note_id: "n1", note_text: "One note." });
    const notes = deriveNotes([e, e]); // same event_id twice = a reconnect replay
    expect(notes).toHaveLength(1);
  });

  it("collapses a refinement onto its note — changes in place, no duplicate", () => {
    const notes = deriveNotes([
      ev("note.emerged", { note_id: "n1", note_text: "Acme is small." }),
      ev("note.refined", { note_id: "n1", previous_text: "Acme is small.", new_text: "Acme is mid-sized.", refinement_reason: "challenge_resolved" }),
    ]);
    expect(notes).toHaveLength(1);
    expect(notes[0].text).toBe("Acme is mid-sized.");
    expect(notes[0].previousText).toBe("Acme is small.");
    expect(notes[0].refinements).toBe(1);
  });

  it("turns an in-book FloatMenu NOTE (marginalia.noted) into a user-sourced insight row (M3)", () => {
    // Read SPR-07 M3 — the in-book NOTE must render, tagged user-sourced so it
    // is never conflated with a model-distilled note (§9).
    const notes = deriveNotes([
      ev("marginalia.noted", {
        note_id: "mn-1",
        note_text: "Provenance is the moat.",
        excerpt: "the moat",
        source_kind: "user",
        chunk_id: null,
      }),
    ]);
    expect(notes).toHaveLength(1);
    expect(notes[0].kind).toBe("insight");
    expect(notes[0].text).toBe("Provenance is the moat.");
    expect(notes[0].sourceKind).toBe("user");
  });

  it("§9 — a model-emerged note carries no user source_kind (never conflated)", () => {
    const notes = deriveNotes([
      ev("note.emerged", { note_id: "n1", note_text: "Model-distilled note." }),
    ]);
    expect(notes[0].sourceKind).toBeNull();
  });
});

describe("NotesPanel — render (M1)", () => {
  it("shows notes as they land, in plain language", () => {
    render(<NotesPanel investigation={state([
      ev("note.emerged", { note_id: "n1", note_text: "Capital is abundant.", confidence: "moderate" }),
    ])} />);
    expect(screen.getByText("Capital is abundant.")).toBeTruthy();
    // confidence renders as a human word, never the raw enum token.
    expect(screen.getByText("fairly grounded")).toBeTruthy();
    expect(screen.queryByText("moderate")).toBeNull();
  });

  it("shows the honest empty state while running, not a fabricated note", () => {
    render(<NotesPanel investigation={state([])} />);
    expect(screen.getByText(/Notes will appear here/)).toBeTruthy();
  });
});

describe("NotesPanel — living note + challenge (M3 + M4)", () => {
  function withNode() {
    return state([
      ev("note.emerged", { note_id: "n1", note_text: "Acme is small.", node_id: "node-1" }),
    ]);
  }

  it("see-what-changed reveals the prior text after a refinement", () => {
    render(<NotesPanel investigation={state([
      ev("note.emerged", { note_id: "n1", note_text: "v1", node_id: "node-1" }),
      ev("note.refined", { note_id: "n1", previous_text: "v1", new_text: "v2", refinement_reason: "challenge_resolved" }),
    ])} />);
    expect(screen.getByText("v2")).toBeTruthy();
    fireEvent.click(screen.getByText("see what changed"));
    expect(screen.getByText(/was: v1/)).toBeTruthy();
  });

  it("challenge that resolves shows the note changed (no duplicate)", async () => {
    challengeNoteMock.mockResolvedValue({
      node_id: "node-1", applied: true, superseded: false, new_text: "Acme is mid-sized.",
      escalated: false, reserved_child_investigation_id: null,
    });
    render(<NotesPanel investigation={withNode()} />);
    fireEvent.click(screen.getByText("challenge this"));
    await waitFor(() => expect(screen.getByText(/the note changed/)).toBeTruthy());
    expect(challengeNoteMock).toHaveBeenCalledWith("node-1", { investigation_id: "inv-test" });
    // Still one note rendered — mutated in place, not duplicated.
    expect(screen.getAllByText("Acme is mid-sized.")).toHaveLength(1);
  });

  it("unresolvable challenge surfaces 'this needs more research' (escalation)", async () => {
    challengeNoteMock.mockResolvedValue({
      node_id: "node-1", applied: false, superseded: false, new_text: null,
      escalated: true, reserved_child_investigation_id: "inv-reserved",
    });
    render(<NotesPanel investigation={withNode()} />);
    fireEvent.click(screen.getByText("challenge this"));
    await waitFor(() => expect(screen.getByText(/this needs more research/)).toBeTruthy());
  });

  it("a 503 (no model) shows the honest no-key state, not a fabricated change", async () => {
    challengeNoteMock.mockImplementation(async () => {
      throw new ApiError("no provider", 503, "no model");
    });
    render(<NotesPanel investigation={withNode()} />);
    fireEvent.click(screen.getByText("challenge this"));
    await waitFor(() => expect(screen.getByText(/model provider isn/)).toBeTruthy());
    // The note text is untouched — no fabricated refinement.
    expect(screen.getByText("Acme is small.")).toBeTruthy();
  });

  it("offers no challenge gesture when the note has no graph node", () => {
    render(<NotesPanel investigation={state([
      ev("note.emerged", { note_id: "n1", note_text: "ungrounded note" }),
    ])} />);
    expect(screen.queryByText("challenge this")).toBeNull();
  });
});
