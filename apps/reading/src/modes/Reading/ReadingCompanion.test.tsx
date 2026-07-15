import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { Event } from "../../generated/types";
import type { InvestigationState } from "../../hooks/useInvestigation";

/**
 * ReadingCompanion.test — the Read glass-box (Read SPR-06 M2).
 *
 * The companion is a READ/DISPLAY layer over the book's reading thread. We
 * mock useInvestigation (the same hook the Research notes rail uses) so the
 * three load-bearing claims are mechanically checkable:
 *
 *  - notes for the book accrue, GROUNDED in the thread's events (reuse of
 *    SPR-03's deriveNotes), and rendered jargon-free;
 *  - with NO key the thread is empty/not-running → the companion shows its
 *    honest empty state, never a fabricated note (the no-key half of the
 *    honest-no-key gate);
 *  - the "AI is working" beat shows only while the thread is genuinely
 *    running, not as decoration.
 */

const { useInvestigationMock, investigationList, previewComposeMock, createComposeMock } = vi.hoisted(() => ({
  useInvestigationMock: vi.fn(),
  investigationList: { investigations: [] as Array<Record<string, unknown>> },
  previewComposeMock: vi.fn(),
  createComposeMock: vi.fn(),
}));

vi.mock("../../hooks/useInvestigation", () => ({
  useInvestigation: useInvestigationMock,
}));
vi.mock("../../hooks/useInvestigationList", () => ({
  useInvestigationList: () => ({ ...investigationList, loading: false, error: null, refetch: vi.fn() }),
}));
vi.mock("../../api/research", () => ({
  previewResearchCompose: previewComposeMock,
  createResearchCompose: createComposeMock,
}));

import ReadingCompanion from "./ReadingCompanion";

function ev(action_type: string, payload: Record<string, unknown>): Event {
  return {
    event_id: "e-" + Math.random().toString(36).slice(2, 8),
    investigation_id: "read-doc-1",
    action_type,
    emitted_at: "2026-05-26T00:00:00Z",
    payload,
    role: "note_taker",
  } as unknown as Event;
}

function state(over: Partial<InvestigationState>): InvestigationState {
  return {
    id: "read-doc-1",
    status: "completed",
    events: [],
    question: null,
    terminalPayload: null,
    costTotal: 0,
    completedAt: null,
    reconnects: 0,
    ...over,
  } as InvestigationState;
}

beforeEach(() => {
  useInvestigationMock.mockReset();
  previewComposeMock.mockReset();
  createComposeMock.mockReset();
  investigationList.investigations = [];
});
afterEach(() => cleanup());

function renderCompanion() {
  return render(
    <ReadingCompanion documentId="doc-1" title="Meditations" readingThreadId="read-doc-1" />,
  );
}

describe("ReadingCompanion (Read SPR-06 M2)", () => {
  it("subscribes to the book's reading thread (one shared thread)", () => {
    useInvestigationMock.mockReturnValue(state({}));
    renderCompanion();
    expect(useInvestigationMock).toHaveBeenCalledWith("read-doc-1");
  });

  it("shows the book's notes + open questions, grounded in the thread events", () => {
    useInvestigationMock.mockReturnValue(
      state({
        status: "completed",
        events: [
          ev("note.emerged", {
            note_id: "n1",
            note_text: "Stoicism frames virtue as the only good.",
            confidence: "high",
          }),
          ev("question.identified", {
            question_id: "q1",
            question_text: "How does this differ from Epicurean ataraxia?",
          }),
        ],
      }),
    );
    renderCompanion();
    expect(screen.getByText(/Stoicism frames virtue/)).toBeTruthy();
    expect(screen.getByText(/Epicurean ataraxia/)).toBeTruthy();
    expect(screen.getByText(/Open question:/)).toBeTruthy();
  });

  it("renders an in-book FloatMenu NOTE (marginalia.noted) as a user-sourced note (M3)", () => {
    // Read SPR-07 M3 — the in-book NOTE lands on the book's reading thread as
    // a marginalia.noted event; the companion (via deriveNotes) must render it,
    // labelled as the reader's own note (§9 — never shown as AI-distilled).
    useInvestigationMock.mockReturnValue(
      state({
        status: "completed",
        events: [
          ev("marginalia.noted", {
            note_id: "mn-1",
            note_text: "The moat is provenance, not the model.",
            excerpt: "provenance is the moat",
            source_kind: "user",
            chunk_id: null,
          }),
        ],
      }),
    );
    renderCompanion();
    expect(screen.getByText(/The moat is provenance/)).toBeTruthy();
    // Honest attribution: a user-authored note carries the "Your note" label.
    expect(screen.getByText(/Your note/)).toBeTruthy();
  });

  it("with no key (empty, not-running thread) shows the honest empty state, no fabricated notes", () => {
    // No provider key ⇒ no distillation emits ⇒ the thread is empty and not
    // running. The companion is calm and honest — never invents a note.
    useInvestigationMock.mockReturnValue(state({ status: "not_found", events: [] }));
    renderCompanion();
    expect(screen.getByText(/No notes yet/)).toBeTruthy();
    // The "AI is working" beat must NOT show for a not-running thread.
    expect(screen.queryByRole("status", { name: /AI is working/i })).toBeNull();
  });

  it("shows the shared working beat only while the thread is running", () => {
    useInvestigationMock.mockReturnValue(state({ status: "in_progress", events: [] }));
    renderCompanion();
    expect(screen.getByRole("status", { name: /AI is working/i })).toBeTruthy();
  });

  it("never leaks the raw thread id as a label (copy discipline)", () => {
    useInvestigationMock.mockReturnValue(state({}));
    const { container } = renderCompanion();
    // The reading-thread id is passed to the hook, never rendered.
    expect(container.textContent).not.toContain("read-doc-1");
    expect(container.textContent).not.toMatch(/inv-/);
  });

  it("keeps an explicitly empty chase selection empty and disables review", () => {
    useInvestigationMock.mockReturnValue(state({}));
    investigationList.investigations = [
      { investigation_id: "chase-one", question: "Origins of the dichotomy", status: "completed", parent_investigation_id: "read-doc-1" },
      { investigation_id: "chase-two", question: "The role of assent", status: "completed", parent_investigation_id: "read-doc-1" },
    ];
    const view = renderCompanion();
    const first = screen.getByRole("checkbox", { name: "Origins of the dichotomy" }) as HTMLInputElement;
    const second = screen.getByRole("checkbox", { name: "The role of assent" }) as HTMLInputElement;
    expect(first.checked).toBe(true);
    expect(second.checked).toBe(true);
    fireEvent.click(first);
    fireEvent.click(second);
    expect(first.checked).toBe(false);
    expect(second.checked).toBe(false);
    investigationList.investigations = [
      ...investigationList.investigations,
      { investigation_id: "chase-three", question: "A newly completed chase", status: "completed", parent_investigation_id: "read-doc-1" },
    ];
    view.rerender(
      <ReadingCompanion documentId="doc-1" title="Meditations" readingThreadId="read-doc-1" />,
    );
    expect((screen.getByRole("checkbox", { name: "A newly completed chase" }) as HTMLInputElement).checked).toBe(false);
    expect((screen.getByRole("button", { name: "Review selected chases" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("reviews and creates the exact selected completed chases in document order", async () => {
    useInvestigationMock.mockReturnValue(state({}));
    investigationList.investigations = [
      { investigation_id: "chase-three", question: "Third", status: "completed", parent_investigation_id: "read-doc-1" },
      { investigation_id: "chase-live", question: "Still working", status: "in_progress", parent_investigation_id: "read-doc-1" },
      { investigation_id: "chase-one", question: "First", status: "completed", parent_investigation_id: "read-doc-1" },
      { investigation_id: "chase-two", question: "Second", status: "completed", parent_investigation_id: "read-doc-1" },
    ];
    previewComposeMock.mockResolvedValue({ compose_id: "preview", selection_fingerprint: "hash", members: [{ investigation_id: "chase-three", content_hash: "3" }, { investigation_id: "chase-two", content_hash: "2" }], identical_content: [], view_url: null, reused: false });
    createComposeMock.mockResolvedValue({ compose_id: "created", selection_fingerprint: "hash", members: [], identical_content: [], view_url: "/research/artifact-composes/created/view", reused: false });
    renderCompanion();
    fireEvent.click(screen.getByRole("checkbox", { name: "First" }));
    fireEvent.click(screen.getByRole("button", { name: "Review selected chases" }));
    await waitFor(() => expect(previewComposeMock).toHaveBeenCalledWith(["chase-three", "chase-two"]));
    fireEvent.click(await screen.findByRole("button", { name: "Create collective reading" }));
    await waitFor(() => expect(createComposeMock).toHaveBeenCalledWith(["chase-three", "chase-two"], "hash"));
    expect((await screen.findByRole("link", { name: /Open collective reading/ })).getAttribute("href")).toBe("/research/artifact-composes/created/view");
  });
});
