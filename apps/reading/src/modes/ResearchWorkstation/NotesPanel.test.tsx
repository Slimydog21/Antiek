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

  it("does not let a distinct duplicate emergence regress an authoritative note", () => {
    const notes = deriveNotes([
      ev("note.emerged", { note_id: "n1", note_text: "v1", node_id: "node-1" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "v1", new_text: "v2", refinement_reason: "challenge_resolved", sequence: 1, previous_sequence: -1, outcome: "applied" }),
      ev("note.emerged", { note_id: "n1", note_text: "regressed", node_id: "node-1" }),
    ]);
    expect(notes[0].text).toBe("v2");
    expect(notes[0].lastAppliedSequence).toBe(1);
  });

  it("preserves first-write identity across note, question, and marginalia collisions", () => {
    const emergedFirst = deriveNotes([
      ev("note.emerged", { note_id: "shared", note_text: "Model note" }),
      ev("question.identified", { question_id: "shared", question_text: "Forged question" }),
      ev("marginalia.noted", { note_id: "shared", note_text: "Forged user note", source_kind: "user" }),
    ]);
    expect(emergedFirst.map((note) => [note.kind, note.text, note.sourceKind])).toEqual([
      ["insight", "Model note", null],
    ]);

    const questionFirst = deriveNotes([
      ev("question.identified", { question_id: "shared", question_text: "Question" }),
      ev("note.emerged", { note_id: "shared", note_text: "Forged model note" }),
    ]);
    expect(questionFirst.map((note) => [note.kind, note.text])).toEqual([
      ["question", "Question"],
    ]);
  });

  it("collapses a refinement onto its note — changes in place, no duplicate", () => {
    const notes = deriveNotes([
      ev("note.emerged", { note_id: "n1", note_text: "Acme is small." }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "Acme is small.", new_text: "Acme is mid-sized.", refinement_reason: "challenge_resolved", sequence: 1, previous_sequence: -1, outcome: "applied" }),
    ]);
    expect(notes).toHaveLength(1);
    expect(notes[0].text).toBe("Acme is mid-sized.");
    expect(notes[0].previousText).toBe("Acme is small.");
    expect(notes[0].refinements).toBe(1);
  });

  it("never lets a superseded attempt replace the settled note", () => {
    const notes = deriveNotes([
      ev("note.emerged", { note_id: "n1", note_text: "v1", node_id: "node-1" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "v1", new_text: "winner", refinement_reason: "challenge_resolved", sequence: 2, previous_sequence: -1, outcome: "applied" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "winner", new_text: "loser", refinement_reason: "background", sequence: 1, previous_sequence: 2, outcome: "superseded" }),
    ]);
    expect(notes[0].text).toBe("winner");
    expect(notes[0].refinements).toBe(1);
  });

  it("uses a first superseded outcome to rebase legacy visible text", () => {
    const notes = deriveNotes([
      ev("note.emerged", { note_id: "n1", note_text: "old" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "settled", new_text: "loser", refinement_reason: "background", sequence: 2, previous_sequence: 4, outcome: "superseded" }),
    ]);
    expect(notes[0].text).toBe("settled");
    expect(notes[0].nodeId).toBe("node-1");
    expect(notes[0].refinements).toBe(0);
  });

  it("ignores ambiguous legacy and reordered applied outcomes", () => {
    const notes = deriveNotes([
      ev("note.emerged", { note_id: "n1", note_text: "v1", node_id: "node-1" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "v1", new_text: "v3", refinement_reason: "challenge_resolved", sequence: 3, previous_sequence: -1, outcome: "applied" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "v1", new_text: "v2", refinement_reason: "challenge_resolved", sequence: 2, previous_sequence: -1, outcome: "applied" }),
      ev("note.refined", { note_id: "n1", previous_text: "v3", new_text: "legacy", refinement_reason: "legacy" }),
    ]);
    expect(notes[0].text).toBe("v3");
    expect(notes[0].refinements).toBe(1);
  });

  it("rejects a graph identity substitution and broken authority chain", () => {
    const notes = deriveNotes([
      ev("note.emerged", { note_id: "n1", note_text: "v1", node_id: "node-1" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "v1", new_text: "v2", refinement_reason: "challenge_resolved", sequence: 2, previous_sequence: -1, outcome: "applied" }),
      ev("note.refined", { note_id: "node-other", origin_note_id: "n1", previous_text: "v2", new_text: "substitution", refinement_reason: "challenge_resolved", sequence: 3, previous_sequence: 2, outcome: "applied" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "v2", new_text: "broken", refinement_reason: "challenge_resolved", sequence: 4, previous_sequence: 3, outcome: "applied" }),
    ]);
    expect(notes[0].text).toBe("v2");
    expect(notes[0].refinements).toBe(1);
  });

  it("ignores exact replay, partial authority, and unknown origins", () => {
    const applied = ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "v1", new_text: "v2", refinement_reason: "challenge_resolved", sequence: 2, previous_sequence: -1, outcome: "applied" });
    const notes = deriveNotes([
      ev("note.emerged", { note_id: "n1", note_text: "v1", node_id: "node-1" }),
      applied,
      applied,
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "v2", new_text: "partial", refinement_reason: "challenge_resolved", sequence: 3, outcome: "applied" }),
      ev("note.refined", { note_id: "node-2", origin_note_id: "missing", previous_text: "x", new_text: "y", refinement_reason: "challenge_resolved", sequence: 1, previous_sequence: -1, outcome: "applied" }),
    ]);
    expect(notes).toHaveLength(1);
    expect(notes[0].text).toBe("v2");
    expect(notes[0].refinements).toBe(1);
  });

  it("cannot apply a refinement to a question or user marginalia row", () => {
    const notes = deriveNotes([
      ev("question.identified", { question_id: "q1", question_text: "Question" }),
      ev("marginalia.noted", { note_id: "m1", note_text: "User note", source_kind: "user" }),
      ev("note.refined", { note_id: "node-q", origin_note_id: "q1", previous_text: "Question", new_text: "forged question", refinement_reason: "bad", sequence: 1, previous_sequence: -1, outcome: "applied" }),
      ev("note.refined", { note_id: "node-m", origin_note_id: "m1", previous_text: "User note", new_text: "forged marginalia", refinement_reason: "bad", sequence: 1, previous_sequence: -1, outcome: "applied" }),
    ]);
    expect(notes.map((note) => note.text)).toEqual(["Question", "User note"]);
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
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "v1", new_text: "v2", refinement_reason: "challenge_resolved", sequence: 1, previous_sequence: -1, outcome: "applied" }),
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

  it("lets later authoritative events replace optimistic challenge text", async () => {
    challengeNoteMock.mockResolvedValue({
      node_id: "node-1", applied: true, superseded: false, new_text: "optimistic",
      escalated: false, reserved_child_investigation_id: null,
    });
    const initial = withNode();
    const view = render(<NotesPanel investigation={initial} />);
    fireEvent.click(screen.getByText("challenge this"));
    await waitFor(() => expect(screen.getByText("optimistic")).toBeTruthy());

    view.rerender(<NotesPanel investigation={state([
      ...initial.events,
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "Acme is small.", new_text: "durable", refinement_reason: "challenge_resolved", sequence: 1, previous_sequence: -1, outcome: "applied" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "durable", new_text: "newer", refinement_reason: "background", sequence: 2, previous_sequence: 1, outcome: "applied" }),
    ])} />);
    await waitFor(() => expect(screen.getByText("newer")).toBeTruthy());
    expect(screen.queryByText("optimistic")).toBeNull();
    expect(screen.queryByText(/the note changed/)).toBeNull();
  });

  it("clears optimism when authority advances to identical base text", async () => {
    challengeNoteMock.mockResolvedValue({
      node_id: "node-1", applied: true, superseded: false, new_text: "optimistic",
      escalated: false, reserved_child_investigation_id: null,
    });
    const initial = withNode();
    const view = render(<NotesPanel investigation={initial} />);
    fireEvent.click(screen.getByText("challenge this"));
    await waitFor(() => expect(screen.getByText("optimistic")).toBeTruthy());

    view.rerender(<NotesPanel investigation={state([
      ...initial.events,
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "Acme is small.", new_text: "Acme is small.", refinement_reason: "normalization", sequence: 1, previous_sequence: -1, outcome: "applied" }),
    ])} />);
    await waitFor(() => expect(screen.queryByText("optimistic")).toBeNull());
    expect(screen.getByText("Acme is small.")).toBeTruthy();
    expect(screen.queryByText(/the note changed/)).toBeNull();
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
