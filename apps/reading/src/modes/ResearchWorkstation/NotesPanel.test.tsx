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

const { challengeNoteMock, getNoteHistoryMock } = vi.hoisted(() => ({
  challengeNoteMock: vi.fn(),
  getNoteHistoryMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    challengeNote: challengeNoteMock,
    getNoteHistory: getNoteHistoryMock,
  };
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
  getNoteHistoryMock.mockReset();
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

  it("folds interleaved observation refinements by the node-global sequence", () => {
    const notes = deriveNotes([
      ev("note.emerged", { note_id: "a", note_text: "Shared v0", node_id: "node-1" }),
      ev("note.emerged", { note_id: "b", note_text: "Shared v0", node_id: "node-1" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "a", previous_text: "Shared v0", new_text: "Shared v1", refinement_reason: "challenge_resolved", sequence: 1, previous_sequence: -1, outcome: "applied" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "b", previous_text: "Shared v1", new_text: "Shared v2", refinement_reason: "challenge_resolved", sequence: 2, previous_sequence: 1, outcome: "applied" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "a", previous_text: "Shared v2", new_text: "Shared v3", refinement_reason: "challenge_resolved", sequence: 3, previous_sequence: 2, outcome: "applied" }),
    ]);
    expect(notes.find((note) => note.noteId === "a")?.text).toBe("Shared v3");
    expect(notes.find((note) => note.noteId === "a")?.lastAppliedSequence).toBe(3);
    expect(notes.find((note) => note.noteId === "b")?.text).toBe("Shared v3");
    expect(notes.find((note) => note.noteId === "a")?.refinements).toBe(3);
    expect(notes.find((note) => note.noteId === "b")?.refinements).toBe(3);
    expect(notes.find((note) => note.noteId === "a")?.observationText).toBe("Shared v0");
    expect(notes.find((note) => note.noteId === "b")?.observationText).toBe("Shared v0");
  });

  it("rebases a later observation onto already-known canonical node truth", () => {
    const notes = deriveNotes([
      ev("note.emerged", { note_id: "a", note_text: "Observed v0", node_id: "node-1" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "a", previous_text: "Observed v0", new_text: "Canonical v1", refinement_reason: "challenge_resolved", sequence: 1, previous_sequence: -1, outcome: "applied" }),
      ev("note.emerged", { note_id: "b", note_text: "Later observation", node_id: "node-1" }),
    ]);
    const later = notes.find((note) => note.noteId === "b");
    expect(later?.text).toBe("Canonical v1");
    expect(later?.observationText).toBe("Later observation");
    expect(later?.refinements).toBe(1);
    expect(later?.lastAppliedSequence).toBe(1);
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

  it("does not trust a first superseded outcome without known canonical text", () => {
    const notes = deriveNotes([
      ev("note.emerged", { note_id: "n1", note_text: "old" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "settled", new_text: "loser", refinement_reason: "background", sequence: 2, previous_sequence: 4, outcome: "superseded" }),
    ]);
    expect(notes[0].text).toBe("old");
    expect(notes[0].nodeId).toBeNull();
    expect(notes[0].refinements).toBe(0);
  });

  it("rejects a coherent-sequence event whose prior text contradicts canonical truth", () => {
    const notes = deriveNotes([
      ev("note.emerged", { note_id: "a", note_text: "v1", node_id: "node-1" }),
      ev("note.emerged", { note_id: "b", note_text: "v1", node_id: "node-1" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "a", previous_text: "v1", new_text: "v2", refinement_reason: "challenge_resolved", sequence: 1, previous_sequence: -1, outcome: "applied" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "b", previous_text: "forged", new_text: "loser", refinement_reason: "background", sequence: 2, previous_sequence: 1, outcome: "applied" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "a", previous_text: "forged", new_text: "loser", refinement_reason: "background", sequence: 0, previous_sequence: 1, outcome: "superseded" }),
    ]);
    expect(notes.map((note) => note.text)).toEqual(["v2", "v2"]);
    expect(notes.map((note) => note.refinements)).toEqual([1, 1]);
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

  it("reveals immutable observed wording after canonical refinement", () => {
    render(<NotesPanel investigation={state([
      ev("note.emerged", { note_id: "n1", note_text: "v1", node_id: "node-1" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "v1", new_text: "v2", refinement_reason: "challenge_resolved", sequence: 1, previous_sequence: -1, outcome: "applied" }),
    ])} />);
    expect(screen.getByText("v2")).toBeTruthy();
    fireEvent.click(screen.getByText("see observed wording"));
    expect(screen.getByText(/observed as: v1/)).toBeTruthy();
  });

  it("shows one canonical truth across aliases without erasing observations", () => {
    render(<NotesPanel investigation={state([
      ev("note.emerged", { note_id: "a", note_text: "Observation A", node_id: "node-1" }),
      ev("note.emerged", { note_id: "b", note_text: "Observation B", node_id: "node-1" }),
      ev("note.emerged", { note_id: "c", note_text: "Other node", node_id: "node-2" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "a", previous_text: "Observation A", new_text: "Canonical truth", refinement_reason: "challenge_resolved", sequence: 1, previous_sequence: -1, outcome: "applied" }),
    ])} />);
    expect(screen.getAllByText("Canonical truth")).toHaveLength(2);
    expect(screen.getByText("Other node")).toBeTruthy();
    expect(screen.getAllByText("see observed wording")).toHaveLength(2);
  });

  it("loads and caches authoritative history lazily", async () => {
    getNoteHistoryMock.mockResolvedValue({
      investigation_id: "inv-test", node_id: "node-1", current_text: "v2",
      current_sequence: 1, refinement_count: 1, authoritative_applied_count: 1,
      superseded_count: 0, complete: true,
      entries: [{
        event_id: "history-1", sequence: 1, previous_sequence: -1,
        previous_text: "v1", new_text: "v2", reason: "challenge_resolved",
        outcome: "applied", delivery_state: "delivered", emitted_at: "2026-07-16T00:00:00Z",
      }],
    });
    render(<NotesPanel investigation={state([
      ev("note.emerged", { note_id: "n1", note_text: "v1", node_id: "node-1" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "v1", new_text: "v2", refinement_reason: "challenge_resolved", sequence: 1, previous_sequence: -1, outcome: "applied" }),
    ])} />);
    expect(getNoteHistoryMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("1 change"));
    await waitFor(() => expect(screen.getByText("Changed")).toBeTruthy());
    expect(getNoteHistoryMock).toHaveBeenCalledWith("node-1", "inv-test");
    fireEvent.click(screen.getByText("1 change"));
    fireEvent.click(screen.getByText("1 change"));
    expect(getNoteHistoryMock).toHaveBeenCalledTimes(1);
  });

  it("discards stale history when the investigation changes mid-request", async () => {
    type History = Awaited<ReturnType<typeof import("../../lib/api").getNoteHistory>>;
    let resolveOld!: (value: History) => void;
    let resolveNew!: (value: History) => void;
    getNoteHistoryMock
      .mockImplementationOnce(() => new Promise<History>((resolve) => { resolveOld = resolve; }))
      .mockImplementationOnce(() => new Promise<History>((resolve) => { resolveNew = resolve; }));
    const events = [
      ev("note.emerged", { note_id: "n1", note_text: "v1", node_id: "node-1" }),
      ev("note.refined", { note_id: "node-1", origin_note_id: "n1", previous_text: "v1", new_text: "v2", refinement_reason: "challenge_resolved", sequence: 1, previous_sequence: -1, outcome: "applied" }),
    ];
    const view = render(<NotesPanel investigation={state(events)} />);
    fireEvent.click(screen.getByText("1 change"));

    view.rerender(<NotesPanel investigation={state(events, { id: "inv-new" })} />);
    fireEvent.click(screen.getByText("1 change"));
    resolveNew({
      investigation_id: "inv-new", node_id: "node-1", current_text: "v2",
      current_sequence: 1, refinement_count: 1, authoritative_applied_count: 1,
      superseded_count: 0, complete: true,
      entries: [{
        event_id: "new-history", sequence: 1, previous_sequence: -1,
        previous_text: "new prior", new_text: "new history", reason: "challenge_resolved",
        outcome: "applied", delivery_state: "delivered", emitted_at: "2026-07-16T00:00:00Z",
      }],
    });
    await waitFor(() => expect(screen.getByText("new history")).toBeTruthy());

    resolveOld({
      investigation_id: "inv-test", node_id: "node-1", current_text: "v2",
      current_sequence: 1, refinement_count: 1, authoritative_applied_count: 1,
      superseded_count: 0, complete: true,
      entries: [{
        event_id: "old-history", sequence: 1, previous_sequence: -1,
        previous_text: "old prior", new_text: "stale history", reason: "challenge_resolved",
        outcome: "applied", delivery_state: "delivered", emitted_at: "2026-07-16T00:00:00Z",
      }],
    });
    await waitFor(() => expect(screen.queryByText("stale history")).toBeNull());
    expect(screen.getByText("new history")).toBeTruthy();
    expect(getNoteHistoryMock).toHaveBeenNthCalledWith(2, "node-1", "inv-new");
  });

  it("challenge that resolves shows the note changed (no duplicate)", async () => {
    challengeNoteMock.mockResolvedValue({
      node_id: "node-1", applied: true, superseded: false, new_text: "Acme is mid-sized.",
      escalated: false, reserved_child_investigation_id: null,
    });
    render(<NotesPanel investigation={withNode()} />);
    fireEvent.click(screen.getByText("challenge this"));
    await waitFor(() => expect(screen.getByText(/the note changed/)).toBeTruthy());
    expect(challengeNoteMock).toHaveBeenCalledWith("node-1", {
      investigation_id: "inv-test",
      idempotency_key: expect.any(String),
      origin_note_id: "n1",
    });
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
    const firstKey = challengeNoteMock.mock.calls[0][1].idempotency_key;
    fireEvent.click(screen.getByText("Try again"));
    await waitFor(() => expect(challengeNoteMock).toHaveBeenCalledTimes(2));
    expect(challengeNoteMock.mock.calls[1][1].idempotency_key).toBe(firstKey);
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
