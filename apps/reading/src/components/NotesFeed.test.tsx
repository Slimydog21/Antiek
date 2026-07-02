import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Event } from "../generated/types";
import NotesFeed from "./NotesFeed";

afterEach(() => cleanup());

const noteEvent = (payload: Record<string, unknown>): Event =>
  ({
    event_id: "event-note-1",
    investigation_id: "inv-1",
    document_id: " doc-1 ",
    action_type: "note.emerged",
    emitted_at: "2026-07-01T12:00:00Z",
    role: "system",
    payload: {
      action_type: "note.emerged",
      note_id: "note-1",
      note_text: "A useful note.",
      source_event_ids: ["event-source-1"],
      confidence: "high",
      ...payload,
    },
  }) as unknown as Event;

describe("NotesFeed", () => {
  it("sanitizes malformed note payload fields before rendering", () => {
    render(
      <NotesFeed
        events={[
          noteEvent({
            note_text: " ",
            confidence: "certain",
            source_event_ids: "not-an-array",
          }),
        ]}
      />,
    );

    expect(screen.getByText("note unavailable")).toBeTruthy();
    expect(screen.getByText("unknown")).toBeTruthy();
    expect(screen.queryByText("from:")).toBeNull();
    expect(document.body.textContent).not.toMatch(/undefined|NaN|Infinity/);
  });

  it("keeps valid source ids and jumps with the sanitized id", () => {
    const onCiteJump = vi.fn();

    render(
      <NotesFeed
        events={[
          noteEvent({
            source_event_ids: [" event-source-1 ", "", 42],
          }),
        ]}
        onCiteJump={onCiteJump}
      />,
    );

    fireEvent.click(screen.getByTitle("jump to event-source-1"));

    expect(screen.getByText("A useful note.")).toBeTruthy();
    expect(screen.getByText("high")).toBeTruthy();
    expect(onCiteJump).toHaveBeenCalledWith("event-source-1");
    expect(onCiteJump).toHaveBeenCalledTimes(1);
  });
});
