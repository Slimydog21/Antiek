import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { ingestVoiceNoteMock, useVoiceCaptureMock, trackMock } = vi.hoisted(() => ({
  ingestVoiceNoteMock: vi.fn(),
  useVoiceCaptureMock: vi.fn(),
  trackMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  ingestVoiceNote: ingestVoiceNoteMock,
}));

vi.mock("../../hooks/useVoiceCapture", () => ({
  useVoiceCapture: useVoiceCaptureMock,
}));

vi.mock("../../lib/analytics", () => ({
  track: trackMock,
}));

import { VoiceNoteCapture } from "./VoiceNoteCapture";

function voiceState(over: Record<string, unknown> = {}) {
  return {
    phase: "idle",
    error: null,
    recorderState: "idle",
    result: null,
    start: vi.fn(),
    stopAndCapture: vi.fn(),
    reset: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  ingestVoiceNoteMock.mockReset().mockResolvedValue({
    status: "ingested",
    document_id: "voice-doc-1",
    document_loaded_event_id: "ev-doc-1",
    chunks_written: 1,
    skipped_reason: null,
    title: "Voice note",
  });
  useVoiceCaptureMock.mockReset().mockReturnValue(voiceState());
  trackMock.mockReset();
});

afterEach(cleanup);

describe("VoiceNoteCapture — shared voice-in quick note", () => {
  it("starts the shared voice capture path instead of relying on pasted transcripts only", async () => {
    const start = vi.fn();
    useVoiceCaptureMock.mockReturnValue(voiceState({ start }));

    render(<VoiceNoteCapture investigationId="inv-voice" />);
    await userEvent.click(screen.getByRole("button", { name: "Record" }));

    expect(start).toHaveBeenCalledTimes(1);
    expect(ingestVoiceNoteMock).not.toHaveBeenCalled();
  });

  it("stops capture, fills an editable transcript, then ingests through the voice-note owner", async () => {
    const stopAndCapture = vi.fn().mockResolvedValue({
      transcript: "spoken idea worth keeping",
      transcriptStatus: "ok",
      sourceKind: "user",
      language: "en",
      durationSeconds: 4,
      eventId: "voice-event-1",
      audioRef: "voice-blob://sha256/clip.webm",
    });
    useVoiceCaptureMock.mockReturnValue(
      voiceState({ phase: "recording", recorderState: "recording", stopAndCapture }),
    );

    render(<VoiceNoteCapture investigationId="inv-voice" />);
    await userEvent.click(screen.getByRole("button", { name: "Stop recording" }));

    const transcript = await screen.findByDisplayValue("spoken idea worth keeping");
    await userEvent.clear(transcript);
    await userEvent.type(transcript, "spoken idea, corrected");
    await userEvent.click(screen.getByRole("button", { name: "Add voice note" }));

    await waitFor(() =>
      expect(ingestVoiceNoteMock).toHaveBeenCalledWith({
        transcript: "spoken idea, corrected",
        investigation_id: "inv-voice",
        duration_seconds: 4,
        language: "en",
      }),
    );
    expect(trackMock).toHaveBeenCalledWith("voice_note_ingested");
    expect(screen.getByText(/voice-doc-1/)).toBeTruthy();
  });

  it("does not ingest silent captured audio", async () => {
    const stopAndCapture = vi.fn().mockResolvedValue({
      transcript: "",
      transcriptStatus: "empty",
      sourceKind: "user",
      language: null,
      durationSeconds: 1,
      eventId: "voice-event-empty",
      audioRef: "voice-blob://sha256/empty.webm",
    });
    useVoiceCaptureMock.mockReturnValue(
      voiceState({ phase: "recording", recorderState: "recording", stopAndCapture }),
    );

    render(<VoiceNoteCapture investigationId="inv-voice" />);
    await userEvent.click(screen.getByRole("button", { name: "Stop recording" }));

    await waitFor(() => expect(screen.getByText(/No words were captured/)).toBeTruthy());
    expect(ingestVoiceNoteMock).not.toHaveBeenCalled();
  });

  it("surfaces capture start failures without ingesting a fabricated note", async () => {
    const start = vi.fn().mockRejectedValue(new Error("mic failed"));
    useVoiceCaptureMock.mockReturnValue(voiceState({ start }));

    render(<VoiceNoteCapture investigationId="inv-voice" />);
    await userEvent.click(screen.getByRole("button", { name: "Record" }));

    await waitFor(() => expect(screen.getByText(/Could not capture voice/)).toBeTruthy());
    expect(ingestVoiceNoteMock).not.toHaveBeenCalled();
  });

  it("does not duplicate the microphone-denied alert when the hook also carries an error", () => {
    useVoiceCaptureMock.mockReturnValue(
      voiceState({ recorderState: "denied", error: "Permission denied" }),
    );

    render(<VoiceNoteCapture investigationId="inv-voice" />);

    expect(screen.getByText(/Microphone permission was denied/)).toBeTruthy();
    expect(screen.queryByText("Permission denied")).toBeNull();
  });
});
