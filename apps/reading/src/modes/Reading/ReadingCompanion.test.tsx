import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ComponentProps } from "react";
import { MemoryRouter } from "react-router-dom";

import type { Event } from "../../generated/types";
import type { InvestigationState } from "../../hooks/useInvestigation";
import type { InvestigationSummary } from "../../lib/api";
import {
  buildChaseDraftHandoff,
  clearChaseDraftHandoffs,
  recordChaseDraftHandoff,
} from "../ResearchWorkstation/chaseHandoffs";

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

const {
  useInvestigationMock,
  listState,
  composeResearchArtifactsMock,
  applySourceMergeMock,
  previewSourceMergeMock,
  commitSourceMergeMock,
  restoreSourceMergeMock,
} = vi.hoisted(() => ({
  useInvestigationMock: vi.fn(),
  listState: { investigations: [] as InvestigationSummary[], loading: false, error: null, refetch: vi.fn() },
  composeResearchArtifactsMock: vi.fn(),
  applySourceMergeMock: vi.fn(),
  previewSourceMergeMock: vi.fn(),
  commitSourceMergeMock: vi.fn(),
  restoreSourceMergeMock: vi.fn(),
}));

vi.mock("../../hooks/useInvestigation", () => ({
  useInvestigation: useInvestigationMock,
}));
vi.mock("../../hooks/useInvestigationList", () => ({
  useInvestigationList: () => listState,
}));
vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    API_BASE: "",
    applySourceMerge: applySourceMergeMock,
    commitSourceMerge: commitSourceMergeMock,
    composeResearchArtifacts: composeResearchArtifactsMock,
    previewSourceMerge: previewSourceMergeMock,
    restoreSourceMerge: restoreSourceMergeMock,
  };
});

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
  listState.investigations = [];
  composeResearchArtifactsMock.mockReset();
  applySourceMergeMock.mockReset();
  previewSourceMergeMock.mockReset();
  commitSourceMergeMock.mockReset();
  restoreSourceMergeMock.mockReset();
});
afterEach(() => {
  cleanup();
  clearChaseDraftHandoffs();
});

function renderCompanion(props: Partial<ComponentProps<typeof ReadingCompanion>> = {}) {
  return render(
    <MemoryRouter>
      <ReadingCompanion documentId="doc-1" title="Meditations" readingThreadId="read-doc-1" {...props} />
    </MemoryRouter>,
  );
}

function summary(over: Partial<InvestigationSummary> & { investigation_id: string }): InvestigationSummary {
  return {
    question: null,
    status: "completed",
    started_at: null,
    completed_at: null,
    cost_usd_total: 0,
    parent_investigation_id: "read-doc-1",
    ...over,
  };
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

  it("shows saved book-origin chases and copies a no-spend merge packet", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    recordChaseDraftHandoff(
      buildChaseDraftHandoff({
        childInvestigationId: "inv-child-1",
        parentInvestigationId: "read-doc-1",
        sourcePassage: "Stoic discipline turns attention into a practice.",
      }),
    );
    useInvestigationMock.mockReturnValue(state({ status: "not_found", events: [] }));

    renderCompanion();

    expect(screen.getByRole("region", { name: /Saved research handoffs/i })).toBeTruthy();
    expect(screen.getByText(/Stoic discipline turns attention/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /open research/i }).getAttribute("href")).toBe("/inv/inv-child-1");

    fireEvent.click(screen.getByRole("button", { name: /copy packet/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const payload = JSON.parse(writeText.mock.calls[0][0]);
    expect(payload).toMatchObject({
      kind: "antiek.reader.chase_merge_packet",
      document_id: "doc-1",
      parent_reading_thread_id: "read-doc-1",
      child_investigation_ids: ["inv-child-1"],
      source_passages: ["Stoic discipline turns attention into a practice."],
      no_spend: true,
    });
    expect(payload.next_step).toMatch(/draft a merge/);
    expect(screen.getByRole("button", { name: /copied/i })).toBeTruthy();
  });

  it("distinguishes completed saved chases from chases still working", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    recordChaseDraftHandoff(
      buildChaseDraftHandoff({
        childInvestigationId: "inv-done",
        parentInvestigationId: "read-doc-1",
        sourcePassage: "A completed chase can be exported into a merge draft.",
      }),
    );
    recordChaseDraftHandoff(
      buildChaseDraftHandoff({
        childInvestigationId: "inv-running",
        parentInvestigationId: "read-doc-1",
        sourcePassage: "A running chase should stay visible but not ready.",
      }),
    );
    listState.investigations = [
      summary({ investigation_id: "inv-done", status: "completed" }),
      summary({ investigation_id: "inv-running", status: "in_progress" }),
    ];
    useInvestigationMock.mockReturnValue(state({ status: "not_found", events: [] }));

    renderCompanion();

    expect(screen.getByText("ready to export")).toBeTruthy();
    expect(screen.getByText("still working")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /copy packet/i }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const payload = JSON.parse(writeText.mock.calls[0][0]);
    expect(payload.child_investigation_ids).toEqual(["inv-running", "inv-done"]);
    expect(payload.ready_child_investigation_ids).toEqual(["inv-done"]);
  });

  it("drafts a no-mutation merge from at least two ready saved chases", async () => {
    for (const [childInvestigationId, sourcePassage] of [
      ["inv-ready-a", "First completed chase."],
      ["inv-ready-b", "Second completed chase."],
    ] as const) {
      recordChaseDraftHandoff(
        buildChaseDraftHandoff({
          childInvestigationId,
          parentInvestigationId: "read-doc-1",
          sourcePassage,
        }),
      );
    }
    listState.investigations = [
      summary({ investigation_id: "inv-ready-a", status: "completed" }),
      summary({ investigation_id: "inv-ready-b", status: "completed" }),
    ];
    composeResearchArtifactsMock.mockResolvedValue({
      path: "/tmp/compose.html",
      draft_merge_path: "/tmp/draft-merge.html",
      members: [
        {
          investigation_id: "inv-ready-b",
          content_hash: "hash-b",
          artifact_path: "/tmp/inv-ready-b.html",
          twin_notes_path: "/tmp/inv-ready-b.notes.html",
        },
        {
          investigation_id: "inv-ready-a",
          content_hash: "hash-a",
          artifact_path: "/tmp/inv-ready-a.html",
          twin_notes_path: "/tmp/inv-ready-a.notes.html",
        },
      ],
      hash_conflicts: [],
    });
    useInvestigationMock.mockReturnValue(state({ status: "not_found", events: [] }));

    renderCompanion();

    fireEvent.click(screen.getByRole("button", { name: /draft ready/i }));
    await waitFor(() =>
      expect(composeResearchArtifactsMock).toHaveBeenCalledWith(["inv-ready-b", "inv-ready-a"], true),
    );
    expect(await screen.findByText(/Draft written/)).toBeTruthy();
    expect(screen.getByText("/tmp/draft-merge.html")).toBeTruthy();
    expect(screen.getByText("2 artifacts · 2 notes twins")).toBeTruthy();
    expect(screen.getByText("Review only · book not changed")).toBeTruthy();
    expect(screen.getByText("No hash conflicts")).toBeTruthy();
    expect(screen.getByRole("link", { name: "open" }).getAttribute("href")).toBe(
      "/research/artifacts/compose/draft-merge.html?investigation_ids=inv-ready-b&investigation_ids=inv-ready-a",
    );
  });

  it("keeps source apply disabled until the draft is explicitly reviewed", async () => {
    for (const childInvestigationId of ["inv-apply-a", "inv-apply-b"]) {
      recordChaseDraftHandoff(
        buildChaseDraftHandoff({
          childInvestigationId,
          parentInvestigationId: "read-doc-1",
          sourcePassage: `Completed chase ${childInvestigationId}.`,
        }),
      );
    }
    listState.investigations = [
      summary({ investigation_id: "inv-apply-a", status: "completed" }),
      summary({ investigation_id: "inv-apply-b", status: "completed" }),
    ];
    composeResearchArtifactsMock.mockResolvedValue({
      path: "/tmp/apply-compose.html",
      draft_merge_path: "/tmp/apply-draft.html",
      members: [
        {
          investigation_id: "inv-apply-b",
          content_hash: "hash-b",
          artifact_path: "/tmp/inv-apply-b.html",
          twin_notes_path: "/tmp/inv-apply-b.notes.html",
        },
        {
          investigation_id: "inv-apply-a",
          content_hash: "hash-a",
          artifact_path: "/tmp/inv-apply-a.html",
          twin_notes_path: "/tmp/inv-apply-a.notes.html",
        },
      ],
      hash_conflicts: [],
    });
    useInvestigationMock.mockReturnValue(state({ status: "not_found", events: [] }));

    renderCompanion();
    fireEvent.click(screen.getByRole("button", { name: /draft ready/i }));
    await screen.findByRole("region", { name: /Draft merge receipt/i });

    expect((screen.getByRole("button", { name: /apply receipt/i }) as HTMLButtonElement).disabled).toBe(true);
    expect(applySourceMergeMock).not.toHaveBeenCalled();
  });

  it("records a source merge receipt after review acknowledgement", async () => {
    for (const childInvestigationId of ["inv-apply-ready-a", "inv-apply-ready-b"]) {
      recordChaseDraftHandoff(
        buildChaseDraftHandoff({
          childInvestigationId,
          parentInvestigationId: "read-doc-1",
          sourcePassage: `Completed chase ${childInvestigationId}.`,
        }),
      );
    }
    listState.investigations = [
      summary({ investigation_id: "inv-apply-ready-a", status: "completed" }),
      summary({ investigation_id: "inv-apply-ready-b", status: "completed" }),
    ];
    composeResearchArtifactsMock.mockResolvedValue({
      path: "/tmp/apply-ready-compose.html",
      draft_merge_path: "/tmp/apply-ready-draft.html",
      members: [
        {
          investigation_id: "inv-apply-ready-b",
          content_hash: "hash-b",
          artifact_path: "/tmp/inv-apply-ready-b.html",
          twin_notes_path: "/tmp/inv-apply-ready-b.notes.html",
        },
        {
          investigation_id: "inv-apply-ready-a",
          content_hash: "hash-a",
          artifact_path: "/tmp/inv-apply-ready-a.html",
          twin_notes_path: "/tmp/inv-apply-ready-a.notes.html",
        },
      ],
      hash_conflicts: [],
    });
    applySourceMergeMock.mockResolvedValue({
      status: "applied",
      document_id: "doc-1",
      source_revision_id: "srcmerge-doc-1-abc123",
      twin_revision_id: "twinmerge-doc-1-abc123",
      event_id: "evt-apply",
      member_investigation_ids: ["inv-apply-ready-b", "inv-apply-ready-a"],
      hash_conflicts_acknowledged: false,
    });
    useInvestigationMock.mockReturnValue(state({ status: "not_found", events: [] }));

    renderCompanion();
    fireEvent.click(screen.getByRole("button", { name: /draft ready/i }));
    await screen.findByRole("region", { name: /Draft merge receipt/i });
    fireEvent.click(screen.getByLabelText(/Reviewed draft/i));
    fireEvent.click(screen.getByRole("button", { name: /apply receipt/i }));

    await waitFor(() => expect(applySourceMergeMock).toHaveBeenCalledTimes(1));
    expect(applySourceMergeMock).toHaveBeenCalledWith({
      reviewed_packet: {
        kind: "antiek.reader.source_merge_review_packet",
        document_id: "doc-1",
        title: "Meditations",
        parent_reading_thread_id: "read-doc-1",
        draft_merge_path: "/tmp/apply-ready-draft.html",
        compose_index_path: "/tmp/apply-ready-compose.html",
        member_investigation_ids: ["inv-apply-ready-b", "inv-apply-ready-a"],
        requested_investigation_ids: ["inv-apply-ready-b", "inv-apply-ready-a"],
        hash_conflict_count: 0,
        hash_conflicts: [],
        source_book_mutated: false,
        twin_document_mutated: false,
        no_spend: true,
      },
      expected_content_hashes: {
        "inv-apply-ready-b": "hash-b",
        "inv-apply-ready-a": "hash-a",
      },
      acknowledge_reviewed_draft: true,
      acknowledge_source_book_mutation: true,
      acknowledge_twin_document_mutation: true,
      acknowledge_hash_conflicts: false,
      operator_reviewer: "reader-companion",
    });
    expect(await screen.findByRole("region", { name: /Source merge receipt/i })).toBeTruthy();
    expect(screen.getByText("srcmerge-doc-1-abc123")).toBeTruthy();
    expect(screen.getByText("twinmerge-doc-1-abc123")).toBeTruthy();
    expect(screen.getByText("Book body not rewritten")).toBeTruthy();
  });

  it("previews source merge revision evidence without applying the receipt", async () => {
    for (const childInvestigationId of ["inv-preview-ready-a", "inv-preview-ready-b"]) {
      recordChaseDraftHandoff(
        buildChaseDraftHandoff({
          childInvestigationId,
          parentInvestigationId: "read-doc-1",
          sourcePassage: `Completed chase ${childInvestigationId}.`,
        }),
      );
    }
    listState.investigations = [
      summary({ investigation_id: "inv-preview-ready-a", status: "completed" }),
      summary({ investigation_id: "inv-preview-ready-b", status: "completed" }),
    ];
    composeResearchArtifactsMock.mockResolvedValue({
      path: "/tmp/preview-ready-compose.html",
      draft_merge_path: "/tmp/preview-ready-draft.html",
      members: [
        {
          investigation_id: "inv-preview-ready-b",
          content_hash: "hash-b",
          artifact_path: "/tmp/inv-preview-ready-b.html",
          twin_notes_path: "/tmp/inv-preview-ready-b.notes.html",
        },
        {
          investigation_id: "inv-preview-ready-a",
          content_hash: "hash-a",
          artifact_path: "/tmp/inv-preview-ready-a.html",
          twin_notes_path: "/tmp/inv-preview-ready-a.notes.html",
        },
      ],
      hash_conflicts: [],
    });
    previewSourceMergeMock.mockResolvedValue({
      status: "previewed",
      document_id: "doc-1",
      source_revision_id: "srcmerge-doc-1-preview",
      twin_revision_id: "twinmerge-doc-1-preview",
      member_investigation_ids: ["inv-preview-ready-b", "inv-preview-ready-a"],
      before_source_hash: "before-hash",
      after_source_hash: "after-hash",
      before_twin_hash: "before-twin",
      after_twin_hash: "after-twin",
      source_bytes_before: 22,
      source_bytes_after: 88,
      twin_bytes_after: 44,
      writes_performed: false,
    });
    useInvestigationMock.mockReturnValue(state({ status: "not_found", events: [] }));

    renderCompanion();
    fireEvent.click(screen.getByRole("button", { name: /draft ready/i }));
    await screen.findByRole("region", { name: /Draft merge receipt/i });
    fireEvent.click(screen.getByLabelText(/Reviewed draft/i));
    fireEvent.click(screen.getByRole("button", { name: /^preview$/i }));

    await waitFor(() => expect(previewSourceMergeMock).toHaveBeenCalledTimes(1));
    expect(applySourceMergeMock).not.toHaveBeenCalled();
    expect(previewSourceMergeMock).toHaveBeenCalledWith({
      reviewed_packet: {
        kind: "antiek.reader.source_merge_review_packet",
        document_id: "doc-1",
        title: "Meditations",
        parent_reading_thread_id: "read-doc-1",
        draft_merge_path: "/tmp/preview-ready-draft.html",
        compose_index_path: "/tmp/preview-ready-compose.html",
        member_investigation_ids: ["inv-preview-ready-b", "inv-preview-ready-a"],
        requested_investigation_ids: ["inv-preview-ready-b", "inv-preview-ready-a"],
        hash_conflict_count: 0,
        hash_conflicts: [],
        source_book_mutated: false,
        twin_document_mutated: false,
        no_spend: true,
      },
      expected_content_hashes: {
        "inv-preview-ready-b": "hash-b",
        "inv-preview-ready-a": "hash-a",
      },
      acknowledge_reviewed_draft: true,
      acknowledge_source_book_mutation: true,
      acknowledge_twin_document_mutation: true,
      acknowledge_hash_conflicts: false,
      operator_reviewer: "reader-companion",
    });
    expect(await screen.findByRole("region", { name: /Source merge preview/i })).toBeTruthy();
    expect(screen.getByText("22 → 88 bytes")).toBeTruthy();
    expect(screen.getByText("before before-hash")).toBeTruthy();
    expect(screen.getByText("after after-hash")).toBeTruthy();
    expect(screen.getByText("writes performed false")).toBeTruthy();
  });

  it("commits source merge only after preview acknowledgement", async () => {
    for (const childInvestigationId of ["inv-commit-ready-a", "inv-commit-ready-b"]) {
      recordChaseDraftHandoff(
        buildChaseDraftHandoff({
          childInvestigationId,
          parentInvestigationId: "read-doc-1",
          sourcePassage: `Completed chase ${childInvestigationId}.`,
        }),
      );
    }
    listState.investigations = [
      summary({ investigation_id: "inv-commit-ready-a", status: "completed" }),
      summary({ investigation_id: "inv-commit-ready-b", status: "completed" }),
    ];
    composeResearchArtifactsMock.mockResolvedValue({
      path: "/tmp/commit-ready-compose.html",
      draft_merge_path: "/tmp/commit-ready-draft.html",
      members: [
        {
          investigation_id: "inv-commit-ready-b",
          content_hash: "hash-b",
          artifact_path: "/tmp/inv-commit-ready-b.html",
          twin_notes_path: "/tmp/inv-commit-ready-b.notes.html",
        },
        {
          investigation_id: "inv-commit-ready-a",
          content_hash: "hash-a",
          artifact_path: "/tmp/inv-commit-ready-a.html",
          twin_notes_path: "/tmp/inv-commit-ready-a.notes.html",
        },
      ],
      hash_conflicts: [],
    });
    previewSourceMergeMock.mockResolvedValue({
      status: "previewed",
      document_id: "doc-1",
      source_revision_id: "srcmerge-doc-1-commit",
      twin_revision_id: "twinmerge-doc-1-commit",
      member_investigation_ids: ["inv-commit-ready-b", "inv-commit-ready-a"],
      before_source_hash: "before-hash",
      after_source_hash: "after-hash",
      before_twin_hash: "before-twin",
      after_twin_hash: "after-twin",
      source_bytes_before: 22,
      source_bytes_after: 88,
      twin_bytes_after: 44,
      writes_performed: false,
    });
    commitSourceMergeMock.mockResolvedValue({
      status: "committed",
      document_id: "doc-1",
      source_revision_id: "srcmerge-doc-1-commit",
      twin_revision_id: "twinmerge-doc-1-commit",
      member_investigation_ids: ["inv-commit-ready-b", "inv-commit-ready-a"],
      before_source_hash: "before-hash",
      after_source_hash: "after-hash",
      before_twin_hash: "before-twin",
      after_twin_hash: "after-twin",
      source_bytes_before: 22,
      source_bytes_after: 88,
      twin_bytes_after: 44,
      writes_performed: true,
      event_id: "evt-commit",
    });
    useInvestigationMock.mockReturnValue(state({ status: "not_found", events: [] }));
    const onSourceBodyChanged = vi.fn();

    renderCompanion({ onSourceBodyChanged });
    fireEvent.click(screen.getByRole("button", { name: /draft ready/i }));
    await screen.findByRole("region", { name: /Draft merge receipt/i });
    fireEvent.click(screen.getByLabelText(/Reviewed draft/i));
    fireEvent.click(screen.getByRole("button", { name: /^preview$/i }));
    await screen.findByRole("region", { name: /Source merge preview/i });

    expect((screen.getByRole("button", { name: /rewrite source/i }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/Rewrite source from preview/i));
    fireEvent.click(screen.getByRole("button", { name: /rewrite source/i }));

    await waitFor(() => expect(commitSourceMergeMock).toHaveBeenCalledTimes(1));
    expect(onSourceBodyChanged).toHaveBeenCalledTimes(1);
    expect(commitSourceMergeMock).toHaveBeenCalledWith({
      reviewed_packet: {
        kind: "antiek.reader.source_merge_review_packet",
        document_id: "doc-1",
        title: "Meditations",
        parent_reading_thread_id: "read-doc-1",
        draft_merge_path: "/tmp/commit-ready-draft.html",
        compose_index_path: "/tmp/commit-ready-compose.html",
        member_investigation_ids: ["inv-commit-ready-b", "inv-commit-ready-a"],
        requested_investigation_ids: ["inv-commit-ready-b", "inv-commit-ready-a"],
        hash_conflict_count: 0,
        hash_conflicts: [],
        source_book_mutated: false,
        twin_document_mutated: false,
        no_spend: true,
      },
      expected_content_hashes: {
        "inv-commit-ready-b": "hash-b",
        "inv-commit-ready-a": "hash-a",
      },
      acknowledge_reviewed_draft: true,
      acknowledge_source_book_mutation: true,
      acknowledge_twin_document_mutation: true,
      acknowledge_hash_conflicts: false,
      operator_reviewer: "reader-companion",
      expected_source_revision_id: "srcmerge-doc-1-commit",
      expected_twin_revision_id: "twinmerge-doc-1-commit",
      expected_before_source_hash: "before-hash",
      expected_after_source_hash: "after-hash",
      expected_before_twin_hash: "before-twin",
      expected_after_twin_hash: "after-twin",
      acknowledge_body_rewrite: true,
    });
    expect(await screen.findByRole("region", { name: /Source merge commit/i })).toBeTruthy();
    expect(screen.getByText("Commit committed")).toBeTruthy();
    expect(screen.getByText("evt-commit")).toBeTruthy();
    expect(screen.getByText("writes performed true")).toBeTruthy();
  });

  it("restores source merge only after restore acknowledgement", async () => {
    for (const childInvestigationId of ["inv-restore-ready-a", "inv-restore-ready-b"]) {
      recordChaseDraftHandoff(
        buildChaseDraftHandoff({
          childInvestigationId,
          parentInvestigationId: "read-doc-1",
          sourcePassage: `Completed chase ${childInvestigationId}.`,
        }),
      );
    }
    listState.investigations = [
      summary({ investigation_id: "inv-restore-ready-a", status: "completed" }),
      summary({ investigation_id: "inv-restore-ready-b", status: "completed" }),
    ];
    composeResearchArtifactsMock.mockResolvedValue({
      path: "/tmp/restore-ready-compose.html",
      draft_merge_path: "/tmp/restore-ready-draft.html",
      members: [
        {
          investigation_id: "inv-restore-ready-b",
          content_hash: "hash-b",
          artifact_path: "/tmp/inv-restore-ready-b.html",
          twin_notes_path: "/tmp/inv-restore-ready-b.notes.html",
        },
        {
          investigation_id: "inv-restore-ready-a",
          content_hash: "hash-a",
          artifact_path: "/tmp/inv-restore-ready-a.html",
          twin_notes_path: "/tmp/inv-restore-ready-a.notes.html",
        },
      ],
      hash_conflicts: [],
    });
    previewSourceMergeMock.mockResolvedValue({
      status: "previewed",
      document_id: "doc-1",
      source_revision_id: "srcmerge-doc-1-restore",
      twin_revision_id: "twinmerge-doc-1-restore",
      member_investigation_ids: ["inv-restore-ready-b", "inv-restore-ready-a"],
      before_source_hash: "before-hash",
      after_source_hash: "after-hash",
      before_twin_hash: "before-twin",
      after_twin_hash: "after-twin",
      source_bytes_before: 22,
      source_bytes_after: 88,
      twin_bytes_after: 44,
      writes_performed: false,
    });
    commitSourceMergeMock.mockResolvedValue({
      status: "committed",
      document_id: "doc-1",
      source_revision_id: "srcmerge-doc-1-restore",
      twin_revision_id: "twinmerge-doc-1-restore",
      member_investigation_ids: ["inv-restore-ready-b", "inv-restore-ready-a"],
      before_source_hash: "before-hash",
      after_source_hash: "after-hash",
      before_twin_hash: "before-twin",
      after_twin_hash: "after-twin",
      source_bytes_before: 22,
      source_bytes_after: 88,
      twin_bytes_after: 44,
      writes_performed: true,
      event_id: "evt-commit",
    });
    restoreSourceMergeMock.mockResolvedValue({
      status: "restored",
      document_id: "doc-1",
      source_revision_id: "srcmerge-doc-1-restore",
      twin_revision_id: "twinmerge-doc-1-restore",
      event_id: "evt-restore",
      before_source_hash: "before-hash",
      restored_source_hash: "before-hash",
      writes_performed: true,
    });
    useInvestigationMock.mockReturnValue(state({ status: "not_found", events: [] }));
    const onSourceBodyChanged = vi.fn();

    renderCompanion({ onSourceBodyChanged });
    fireEvent.click(screen.getByRole("button", { name: /draft ready/i }));
    await screen.findByRole("region", { name: /Draft merge receipt/i });
    fireEvent.click(screen.getByLabelText(/Reviewed draft/i));
    fireEvent.click(screen.getByRole("button", { name: /^preview$/i }));
    await screen.findByRole("region", { name: /Source merge preview/i });
    fireEvent.click(screen.getByLabelText(/Rewrite source from preview/i));
    fireEvent.click(screen.getByRole("button", { name: /rewrite source/i }));
    await screen.findByRole("region", { name: /Source merge commit/i });
    expect(onSourceBodyChanged).toHaveBeenCalledTimes(1);

    expect((screen.getByRole("button", { name: /^restore$/i }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/Restore previous source body/i));
    fireEvent.click(screen.getByRole("button", { name: /^restore$/i }));

    await waitFor(() => expect(restoreSourceMergeMock).toHaveBeenCalledTimes(1));
    expect(onSourceBodyChanged).toHaveBeenCalledTimes(2);
    expect(restoreSourceMergeMock).toHaveBeenCalledWith({
      document_id: "doc-1",
      parent_reading_thread_id: "read-doc-1",
      source_revision_id: "srcmerge-doc-1-restore",
      twin_revision_id: "twinmerge-doc-1-restore",
      expected_after_source_hash: "after-hash",
      expected_before_source_hash: "before-hash",
      acknowledge_restore: true,
      operator_reviewer: "reader-companion",
    });
    expect(await screen.findByRole("region", { name: /Source merge restore/i })).toBeTruthy();
    expect(screen.getByText("Restore restored")).toBeTruthy();
    expect(screen.getByText("evt-restore")).toBeTruthy();
  });

  it("requires conflict acknowledgement before applying a conflicted draft", async () => {
    for (const childInvestigationId of ["inv-apply-conflict-a", "inv-apply-conflict-b"]) {
      recordChaseDraftHandoff(
        buildChaseDraftHandoff({
          childInvestigationId,
          parentInvestigationId: "read-doc-1",
          sourcePassage: `Completed chase ${childInvestigationId}.`,
        }),
      );
    }
    listState.investigations = [
      summary({ investigation_id: "inv-apply-conflict-a", status: "completed" }),
      summary({ investigation_id: "inv-apply-conflict-b", status: "completed" }),
    ];
    composeResearchArtifactsMock.mockResolvedValue({
      path: "/tmp/apply-conflict-compose.html",
      draft_merge_path: "/tmp/apply-conflict-draft.html",
      members: [
        {
          investigation_id: "inv-apply-conflict-b",
          content_hash: "same-hash",
          artifact_path: "/tmp/inv-apply-conflict-b.html",
          twin_notes_path: "/tmp/inv-apply-conflict-b.notes.html",
        },
        {
          investigation_id: "inv-apply-conflict-a",
          content_hash: "same-hash",
          artifact_path: "/tmp/inv-apply-conflict-a.html",
          twin_notes_path: "/tmp/inv-apply-conflict-a.notes.html",
        },
      ],
      hash_conflicts: [["inv-apply-conflict-b", "inv-apply-conflict-a"]],
    });
    useInvestigationMock.mockReturnValue(state({ status: "not_found", events: [] }));

    renderCompanion();
    fireEvent.click(screen.getByRole("button", { name: /draft ready/i }));
    await screen.findByRole("region", { name: /Draft merge receipt/i });
    fireEvent.click(screen.getByLabelText(/Reviewed draft/i));

    expect((screen.getByRole("button", { name: /apply receipt/i }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/Conflict reviewed/i));
    expect((screen.getByRole("button", { name: /apply receipt/i }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("copies a source-merge review packet without mutating the book or notes twin", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    for (const childInvestigationId of ["inv-review-a", "inv-review-b"]) {
      recordChaseDraftHandoff(
        buildChaseDraftHandoff({
          childInvestigationId,
          parentInvestigationId: "read-doc-1",
          sourcePassage: `Completed chase ${childInvestigationId}.`,
        }),
      );
    }
    listState.investigations = [
      summary({ investigation_id: "inv-review-a", status: "completed" }),
      summary({ investigation_id: "inv-review-b", status: "completed" }),
    ];
    composeResearchArtifactsMock.mockResolvedValue({
      path: "/tmp/review-compose.html",
      draft_merge_path: "/tmp/review-draft.html",
      members: [
        {
          investigation_id: "inv-review-b",
          content_hash: "hash-b",
          artifact_path: "/tmp/inv-review-b.html",
          twin_notes_path: "/tmp/inv-review-b.notes.html",
        },
        {
          investigation_id: "inv-review-a",
          content_hash: "hash-a",
          artifact_path: "/tmp/inv-review-a.html",
          twin_notes_path: "/tmp/inv-review-a.notes.html",
        },
      ],
      hash_conflicts: [],
    });
    useInvestigationMock.mockReturnValue(state({ status: "not_found", events: [] }));

    renderCompanion();
    fireEvent.click(screen.getByRole("button", { name: /draft ready/i }));
    await screen.findByRole("region", { name: /Draft merge receipt/i });
    fireEvent.click(screen.getByRole("button", { name: /copy review/i }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const payload = JSON.parse(writeText.mock.calls[0][0]);
    expect(payload).toMatchObject({
      kind: "antiek.reader.source_merge_review_packet",
      document_id: "doc-1",
      title: "Meditations",
      parent_reading_thread_id: "read-doc-1",
      draft_merge_path: "/tmp/review-draft.html",
      compose_index_path: "/tmp/review-compose.html",
      member_investigation_ids: ["inv-review-b", "inv-review-a"],
      requested_investigation_ids: ["inv-review-b", "inv-review-a"],
      hash_conflict_count: 0,
      hash_conflicts: [],
      source_book_mutated: false,
      twin_document_mutated: false,
      no_spend: true,
    });
    expect(payload.next_step).toMatch(/before any source book or twin-document mutation/);
    expect(screen.getByRole("button", { name: /copied review/i })).toBeTruthy();
  });

  it("surfaces draft-merge hash conflicts in the Reader receipt and review packet", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    for (const childInvestigationId of ["inv-conflict-a", "inv-conflict-b"]) {
      recordChaseDraftHandoff(
        buildChaseDraftHandoff({
          childInvestigationId,
          parentInvestigationId: "read-doc-1",
          sourcePassage: `Completed chase ${childInvestigationId}.`,
        }),
      );
    }
    listState.investigations = [
      summary({ investigation_id: "inv-conflict-a", status: "completed" }),
      summary({ investigation_id: "inv-conflict-b", status: "completed" }),
    ];
    composeResearchArtifactsMock.mockResolvedValue({
      path: "/tmp/conflict-compose.html",
      draft_merge_path: "/tmp/conflict-draft.html",
      members: [
        {
          investigation_id: "inv-conflict-b",
          content_hash: "same-hash",
          artifact_path: "/tmp/inv-conflict-b.html",
          twin_notes_path: "/tmp/inv-conflict-b.notes.html",
        },
        {
          investigation_id: "inv-conflict-a",
          content_hash: "same-hash",
          artifact_path: "/tmp/inv-conflict-a.html",
          twin_notes_path: "/tmp/inv-conflict-a.notes.html",
        },
      ],
      hash_conflicts: [["inv-conflict-b", "inv-conflict-a"]],
    });
    useInvestigationMock.mockReturnValue(state({ status: "not_found", events: [] }));

    renderCompanion();
    fireEvent.click(screen.getByRole("button", { name: /draft ready/i }));

    expect(await screen.findByText("1 hash conflict need review")).toBeTruthy();
    expect(screen.getByRole("region", { name: /Draft merge receipt/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /copy review/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const payload = JSON.parse(writeText.mock.calls[0][0]);
    expect(payload.hash_conflict_count).toBe(1);
    expect(payload.hash_conflicts).toEqual([["inv-conflict-b", "inv-conflict-a"]]);
    expect(payload.source_book_mutated).toBe(false);
    expect(payload.twin_document_mutated).toBe(false);
  });

  it("keeps draft merge disabled until two chases are ready", () => {
    recordChaseDraftHandoff(
      buildChaseDraftHandoff({
        childInvestigationId: "inv-one-ready",
        parentInvestigationId: "read-doc-1",
        sourcePassage: "Only one completed chase.",
      }),
    );
    listState.investigations = [summary({ investigation_id: "inv-one-ready", status: "completed" })];
    useInvestigationMock.mockReturnValue(state({ status: "not_found", events: [] }));

    renderCompanion();

    expect((screen.getByRole("button", { name: /draft ready/i }) as HTMLButtonElement).disabled).toBe(true);
    expect(composeResearchArtifactsMock).not.toHaveBeenCalled();
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
