import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";

import VoiceNote from "./VoiceNote";

// Mock the recorder hook so we don't need a real mic, and the API client
// so we don't hit the network. The recorder mock lets a test "produce" a
// recorded blob by flipping its returned state.
const recorderState: { state: string; blob: Blob | null; error: string | null } = {
  state: "idle",
  blob: null,
  error: null,
};
const startMock = vi.fn();
const stopMock = vi.fn();
const resetMock = vi.fn();

vi.mock("../../hooks/useVoiceRecorder", () => ({
  useVoiceRecorder: () => ({
    state: recorderState.state,
    blob: recorderState.blob,
    error: recorderState.error,
    start: startMock,
    stop: stopMock,
    reset: resetMock,
  }),
}));

const { transcribeMock, saveMock } = vi.hoisted(() => ({
  transcribeMock: vi.fn(),
  saveMock: vi.fn(),
}));
vi.mock("../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../api/books")>();
  return { ...actual, transcribeAudio: transcribeMock, saveVoiceNote: saveMock };
});

beforeEach(() => {
  recorderState.state = "idle";
  recorderState.blob = null;
  recorderState.error = null;
  startMock.mockClear();
  stopMock.mockClear();
  resetMock.mockClear();
  transcribeMock.mockReset();
  saveMock.mockReset();
});
afterEach(() => cleanup());

describe("VoiceNote", () => {
  it("starts recording when Record is clicked", () => {
    render(<VoiceNote documentId="doc-1" pageIndex={2} investigationId="read-doc-1" />);
    fireEvent.click(screen.getByRole("button", { name: /Record a thought/ }));
    expect(startMock).toHaveBeenCalled();
  });

  it("transcribes a finished recording and lets the reader correct it before saving", async () => {
    transcribeMock.mockResolvedValue({ transcript: "the authr argues X", language: "en", duration_seconds: 3 });
    saveMock.mockResolvedValue({
      voice_note_id: "vnote-1", document_id: "doc-1", page_index: 2,
      note_count: 2, notes: ["insight a", "question b"], emitted_event_ids: ["e1", "e2"],
    });
    // Simulate the recorder finishing with a blob.
    recorderState.state = "stopped";
    recorderState.blob = new Blob(["audio"], { type: "audio/webm" });

    render(<VoiceNote documentId="doc-1" pageIndex={2} investigationId="read-doc-1" />);
    // Auto-transcribes → correction textarea appears with the transcript.
    await waitFor(() =>
      expect(screen.getByLabelText("Voice note transcript (editable)")).toBeTruthy(),
    );
    const ta = screen.getByLabelText("Voice note transcript (editable)") as HTMLTextAreaElement;
    expect(ta.value).toBe("the authr argues X");
    // Reader corrects the misheard word, then saves.
    fireEvent.change(ta, { target: { value: "the author argues X" } });
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));
    await waitFor(() => expect(saveMock).toHaveBeenCalled());
    expect(saveMock).toHaveBeenCalledWith("doc-1", {
      page_index: 2,
      transcript: "the author argues X", // the CORRECTED text, not the raw ASR
      investigation_id: "read-doc-1",
    });
    await waitFor(() => expect(screen.getByText(/2 notes distilled/)).toBeTruthy());
  });

  it("emits living-TV note_saved after a confirmed voice note save", async () => {
    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent<{ experience?: string }>).detail?.experience;
      if (d) seen.push(d);
    };
    window.addEventListener("antiek:werner-experience", onExp);
    transcribeMock.mockResolvedValue({ transcript: "hello" });
    saveMock.mockResolvedValue({
      voice_note_id: "vnote-2",
      document_id: "doc-1",
      page_index: 1,
      note_count: 1,
      notes: ["insight"],
      emitted_event_ids: ["e1"],
    });
    recorderState.state = "stopped";
    recorderState.blob = new Blob(["audio"], { type: "audio/webm" });
    render(
      <VoiceNote documentId="doc-1" pageIndex={1} investigationId="read-doc-1" />,
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Voice note transcript (editable)")).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));
    await waitFor(() => expect(saveMock).toHaveBeenCalled());
    window.removeEventListener("antiek:werner-experience", onExp);
    expect(seen).toContain("note_saved");
  });

  it("falls back to manual typing when transcription is unavailable", async () => {
    transcribeMock.mockRejectedValue(new Error("Transcription isn’t available right now."));
    recorderState.state = "stopped";
    recorderState.blob = new Blob(["audio"], { type: "audio/webm" });
    render(<VoiceNote documentId="doc-1" pageIndex={0} investigationId="read-doc-1" />);
    // Still lands on the correction step (empty), with the error shown.
    await waitFor(() =>
      expect(screen.getByLabelText("Voice note transcript (editable)")).toBeTruthy(),
    );
    expect(screen.getByRole("alert").textContent).toMatch(/available/);
  });
});
