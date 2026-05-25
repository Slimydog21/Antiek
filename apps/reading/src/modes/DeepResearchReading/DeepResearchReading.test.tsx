import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { DocumentNote } from "../../api/reading";
import DocumentView from "./DocumentView";
import NoteCard from "./NoteCard";

const { challengeMock } = vi.hoisted(() => ({ challengeMock: vi.fn() }));
vi.mock("../../api/reading", async (orig) => ({
  ...(await orig<typeof import("../../api/reading")>()),
  challengeNote: challengeMock,
}));

afterEach(() => { cleanup(); challengeMock.mockReset(); });

const INSIGHT: DocumentNote = {
  node_id: "i1", kind: "insight", text: "GPUs gate model scale.", confidence: "high",
  anchors: ["GPUs gate model scale."],
};

describe("NoteCard — living-note challenge", () => {
  it("refines in place when a correction is given", async () => {
    challengeMock.mockResolvedValue({
      node_id: "i1", applied: true, new_text: "GPUs and capital gate model scale.",
      escalated: false, escalated_question_id: null, reserved_child_investigation_id: null,
    });
    const onRefined = vi.fn();
    render(<NoteCard note={INSIGHT} documentId="doc-1" onRefined={onRefined} />);
    fireEvent.click(screen.getByText("challenge this note"));
    fireEvent.change(screen.getByLabelText("challenge text"), { target: { value: "incomplete" } });
    fireEvent.change(screen.getByLabelText("correction text"), { target: { value: "GPUs and capital gate model scale." } });
    fireEvent.click(screen.getByRole("button", { name: "Refine" }));
    await waitFor(() => expect(onRefined).toHaveBeenCalledWith("GPUs and capital gate model scale."));
    expect(challengeMock).toHaveBeenCalledWith("i1", expect.objectContaining({ resolution: "GPUs and capital gate model scale." }));
    expect(screen.getByText("GPUs and capital gate model scale.")).toBeTruthy();
  });

  it("escalates (spin seam) when no correction is given", async () => {
    challengeMock.mockResolvedValue({
      node_id: "i1", applied: false, new_text: null, escalated: true,
      escalated_question_id: "q-9", reserved_child_investigation_id: "inv-reserved",
    });
    const onEscalated = vi.fn();
    render(<NoteCard note={INSIGHT} documentId="doc-1" onEscalated={onEscalated} />);
    fireEvent.click(screen.getByText("challenge this note"));
    fireEvent.change(screen.getByLabelText("challenge text"), { target: { value: "source?" } });
    expect(screen.getByRole("button", { name: /Escalate/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Escalate/ }));
    await waitFor(() => expect(onEscalated).toHaveBeenCalledWith("inv-reserved", "q-9"));
    // The challenge carried NO resolution → backend escalates.
    expect(challengeMock.mock.calls[0][1].resolution).toBeUndefined();
  });
});

describe("DocumentView — inline content-anchored highlights", () => {
  const notes: DocumentNote[] = [
    INSIGHT,
    { node_id: "q1", kind: "question", text: "What is the moat?", confidence: "unknown", anchors: ["Capital is abundant."] },
  ];
  const RAW = "GPUs gate model scale. Capital is abundant.";

  it("renders insight + question highlights and selects on click", () => {
    const onSelect = vi.fn();
    render(<DocumentView rawText={RAW} notes={notes} selectedNoteId={null}
      onSelectNote={onSelect} onSaveEdit={() => {}} />);
    const marks = screen.getAllByRole("button").filter((b) => b.tagName === "MARK");
    expect(marks.length).toBe(2);
    fireEvent.click(marks[0]);
    expect(onSelect).toHaveBeenCalledWith("i1");
  });

  it("enters edit mode and saves a new version", () => {
    const onSave = vi.fn();
    render(<DocumentView rawText={RAW} notes={notes} selectedNoteId={null}
      onSelectNote={() => {}} onSaveEdit={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const editor = screen.getByLabelText("document editor") as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: RAW + " The team is small." } });
    fireEvent.click(screen.getByRole("button", { name: "Save version" }));
    expect(onSave).toHaveBeenCalledWith(RAW + " The team is small.");
  });
});
