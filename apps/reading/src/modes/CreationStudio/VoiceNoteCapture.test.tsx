/**
 * VoiceNoteCapture.test.tsx — the CreationStudio voice-note widget reports an
 * ingest only as far as the backend proved it.
 *
 * /voice-notes/ingest answers `skipped` with `chunks_written: 0` and
 * `skipped_reason: "low_word_count"` for a note too short to keep, and still
 * returns a document_id. Nothing was chunked, so nothing can be cited: the
 * widget must not show the success check or count it as ingested.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const { ingestVoiceNoteMock, trackMock } = vi.hoisted(() => ({
  ingestVoiceNoteMock: vi.fn(),
  trackMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, ingestVoiceNote: ingestVoiceNoteMock };
});

vi.mock("../../lib/analytics", () => ({ track: trackMock }));

import { VoiceNoteCapture } from "./VoiceNoteCapture";

afterEach(() => {
  cleanup();
  ingestVoiceNoteMock.mockReset();
  trackMock.mockReset();
});

function submit(text: string) {
  fireEvent.change(screen.getByPlaceholderText("Transcript…"), {
    target: { value: text },
  });
  fireEvent.click(screen.getByText("Add voice note"));
}

describe("VoiceNoteCapture — ingest verdict", () => {
  it("does not show success or track an ingest when the note was skipped with 0 chunks", async () => {
    ingestVoiceNoteMock.mockResolvedValue({
      status: "skipped",
      document_id: "doc-voice-x",
      document_loaded_event_id: "e",
      chunks_written: 0,
      skipped_reason: "low_word_count",
      title: "Short note",
    });
    render(<VoiceNoteCapture />);
    submit("too short");

    await waitFor(() =>
      expect(screen.getByText(/too little readable text/i)).toBeTruthy(),
    );
    expect(screen.getByText(/Nothing from “Short note” was added/)).toBeTruthy();
    expect(screen.queryByText(/✓/)).toBeNull();
    expect(screen.queryByText(/doc-voice-x/)).toBeNull();
    expect(trackMock).not.toHaveBeenCalledWith("voice_note_ingested");
    // The transcript is kept so the operator can extend it and try again.
    expect(
      (screen.getByPlaceholderText("Transcript…") as HTMLTextAreaElement).value,
    ).toBe("too short");
  });

  it("shows the check and tracks the ingest when chunks were written (control)", async () => {
    ingestVoiceNoteMock.mockResolvedValue({
      status: "ingested",
      document_id: "doc-voice-ok-0123456789",
      document_loaded_event_id: "e",
      chunks_written: 3,
      skipped_reason: null,
      title: "Long note",
    });
    render(<VoiceNoteCapture />);
    submit("a voice note long enough to be chunked into the graph");

    await waitFor(() => expect(screen.getByText(/✓/)).toBeTruthy());
    expect(screen.getByText(/doc-voice-ok-012/)).toBeTruthy();
    expect(trackMock).toHaveBeenCalledWith("voice_note_ingested");
    expect(
      (screen.getByPlaceholderText("Transcript…") as HTMLTextAreaElement).value,
    ).toBe("");
  });
});
