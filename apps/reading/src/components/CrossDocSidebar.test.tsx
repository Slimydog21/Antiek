import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import type { Event } from "../generated/types";
import CrossDocSidebar from "./CrossDocSidebar";

function event(
  id: string,
  actionType: Event["action_type"],
  payload: Record<string, unknown>,
): Event {
  return {
    event_id: id,
    investigation_id: "inv-1",
    action_type: actionType,
    payload: {
      action_type: actionType,
      ...payload,
    } as Event["payload"],
    param_version: "test",
    emitted_at: "2026-07-01T12:00:00Z",
  };
}

afterEach(() => cleanup());

describe("CrossDocSidebar", () => {
  it("drops malformed cross-doc payloads before rendering links or jump targets", () => {
    const onCiteJump = vi.fn();
    render(
      <CrossDocSidebar
        onCiteJump={onCiteJump}
        events={[
          event("q-valid", "question.identified", {
            question_id: " q1 ",
            question_text: " How does the second source answer this? ",
          }),
          event("q-bad", "question.identified", {
            question_id: "",
            question_text: "Should not attach",
          }),
          event("bad-empty-doc", "cross_doc.question_answered", {
            question_id: "q1",
            question_document_id: " ",
            answer_document_id: "doc-answer",
            answer_note_id: "note-bad",
          }),
          event("bad-missing-note", "cross_doc.question_answered", {
            question_id: "q1",
            question_document_id: "doc-question",
            answer_document_id: "doc-answer",
            answer_note_id: "",
          }),
          event("valid-link", "cross_doc.question_answered", {
            question_id: " q1 ",
            question_document_id: " doc-question ",
            answer_document_id: " doc-answer ",
            answer_note_id: " note-valid ",
          }),
        ]}
      />,
    );

    expect(screen.getByText("1 link")).toBeTruthy();
    expect(screen.getByText("\"How does the second source answer this?\"")).toBeTruthy();
    expect(screen.queryByText(/Should not attach/)).toBeNull();

    fireEvent.click(screen.getByTitle("jump to note note-valid"));
    expect(onCiteJump).toHaveBeenCalledWith("note-valid");
  });
});
