import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

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

const { useInvestigationMock } = vi.hoisted(() => ({
  useInvestigationMock: vi.fn(),
}));

vi.mock("../../hooks/useInvestigation", () => ({
  useInvestigation: useInvestigationMock,
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

beforeEach(() => useInvestigationMock.mockReset());
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

  it("renders session thinking brand + living-TV invent chrome (not inventory-only)", () => {
    useInvestigationMock.mockReturnValue(state({}));
    renderCompanion();
    expect(screen.getByTestId("reading-companion")).toBeTruthy();
    expect(screen.getByTestId("reading-companion-werner-brand")).toBeTruthy();
    const livingTv = screen.getByTestId(
      "reading-companion-living-tv-art",
    ) as HTMLImageElement;
    expect(livingTv.getAttribute("src") ?? "").toMatch(
      /werner_living_tv_session_v1/,
    );
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
});
