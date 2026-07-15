import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { transcribe } from "../../api/asr";
import { useVoiceRecorder } from "../../hooks/useVoiceRecorder";
import { VoiceSteeringInput } from "./VoiceSteeringInput";

vi.mock("../../api/asr", () => ({ transcribe: vi.fn() }));
vi.mock("../../hooks/useVoiceRecorder", () => ({ useVoiceRecorder: vi.fn() }));

const mockTranscribe = vi.mocked(transcribe);
const mockRecorder = vi.mocked(useVoiceRecorder);
const start = vi.fn();
const stop = vi.fn();
const reset = vi.fn();
let recorderState: ReturnType<typeof useVoiceRecorder>;

beforeEach(() => {
  start.mockReset();
  stop.mockReset();
  reset.mockReset();
  mockTranscribe.mockReset();
  recorderState = { state: "idle", error: null, blob: null, start, stop, reset };
  mockRecorder.mockImplementation(() => recorderState);
});

afterEach(() => cleanup());

function renderInput(onTranscript = vi.fn()) {
  const props = {
    value: "typed steer",
    rawTranscript: null,
    disabled: false,
    onChange: vi.fn(),
    onTranscript,
    onDiscardTranscript: vi.fn(),
    onBusyChange: vi.fn(),
  };
  return { ...render(<VoiceSteeringInput {...props} />), props };
}

describe("VoiceSteeringInput", () => {
  it("records, transcribes, and returns reviewable raw speech", async () => {
    mockTranscribe.mockResolvedValue({ transcript: "  Go deeper on engines.  ", language: "en", durationSeconds: 3 });
    const onTranscript = vi.fn();
    const view = renderInput(onTranscript);

    fireEvent.click(screen.getByRole("button", { name: "Record voice" }));
    expect(reset).toHaveBeenCalledOnce();
    expect(start).toHaveBeenCalledOnce();
    expect(onTranscript).not.toHaveBeenCalled();

    recorderState = { ...recorderState, state: "stopped", blob: new Blob(["voice"], { type: "audio/webm" }) };
    view.rerender(<VoiceSteeringInput {...view.props} />);

    await waitFor(() => expect(mockTranscribe).toHaveBeenCalledWith(
      recorderState.blob,
      { signal: expect.any(AbortSignal) },
    ));
    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith("Go deeper on engines."));
  });

  it("stops an active recording without applying or transcribing early", () => {
    recorderState = { ...recorderState, state: "recording" };
    renderInput();

    fireEvent.click(screen.getByRole("button", { name: "Stop recording" }));

    expect(stop).toHaveBeenCalledOnce();
    expect(mockTranscribe).not.toHaveBeenCalled();
  });

  it("keeps typed fallback available when microphone permission is denied", () => {
    recorderState = { ...recorderState, state: "denied", error: "denied" };
    renderInput();

    expect(screen.getByRole("alert").textContent).toContain("Microphone permission was denied");
    expect((screen.getByLabelText("Steering prompt") as HTMLTextAreaElement).value).toBe("typed steer");
  });

  it("refuses an empty transcript without inventing steering text", async () => {
    mockTranscribe.mockResolvedValue({ transcript: "   ", language: null, durationSeconds: 1 });
    const onTranscript = vi.fn();
    const view = renderInput(onTranscript);
    recorderState = { ...recorderState, state: "stopped", blob: new Blob(["silence"]) };
    view.rerender(<VoiceSteeringInput {...view.props} />);

    expect((await screen.findByRole("alert")).textContent).toContain("No words were detected");
    expect(onTranscript).not.toHaveBeenCalled();
  });

  it("surfaces unavailable ASR without producing a transcript", async () => {
    mockTranscribe.mockRejectedValue(new Error("Transcription isn't available right now."));
    const onTranscript = vi.fn();
    const view = renderInput(onTranscript);
    recorderState = { ...recorderState, state: "stopped", blob: new Blob(["voice"]) };
    view.rerender(<VoiceSteeringInput {...view.props} />);

    expect((await screen.findByRole("alert")).textContent).toContain("isn't available");
    expect(onTranscript).not.toHaveBeenCalled();
  });

  it("rejects a malformed ASR response without inventing steering text", async () => {
    mockTranscribe.mockResolvedValue({ transcript: undefined } as unknown as Awaited<ReturnType<typeof transcribe>>);
    const onTranscript = vi.fn();
    const view = renderInput(onTranscript);
    recorderState = { ...recorderState, state: "stopped", blob: new Blob(["voice"]) };
    view.rerender(<VoiceSteeringInput {...view.props} />);

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(onTranscript).not.toHaveBeenCalled();
  });

  it("rejects punctuation-only ASR output as no detected words", async () => {
    mockTranscribe.mockResolvedValue({ transcript: "...", language: null, durationSeconds: 1 });
    const onTranscript = vi.fn();
    const view = renderInput(onTranscript);
    recorderState = { ...recorderState, state: "stopped", blob: new Blob(["silence"]) };
    view.rerender(<VoiceSteeringInput {...view.props} />);

    expect((await screen.findByRole("alert")).textContent).toContain("No words were detected");
    expect(onTranscript).not.toHaveBeenCalled();
  });

  it("drops a late transcript after the steering authority unmounts", async () => {
    let resolve!: (value: { transcript: string; language: string; durationSeconds: number }) => void;
    mockTranscribe.mockReturnValue(new Promise((done) => { resolve = done; }));
    const onTranscript = vi.fn();
    const view = renderInput(onTranscript);
    recorderState = { ...recorderState, state: "stopped", blob: new Blob(["voice"]) };
    view.rerender(<VoiceSteeringInput {...view.props} />);
    await waitFor(() => expect(mockTranscribe).toHaveBeenCalledOnce());
    const signal = mockTranscribe.mock.calls[0][1]?.signal;

    view.unmount();
    expect(signal?.aborted).toBe(true);
    resolve({ transcript: "stale revision steer", language: "en", durationSeconds: 2 });
    await Promise.resolve();
    await Promise.resolve();
    expect(onTranscript).not.toHaveBeenCalled();
  });

  it("uses the latest parent callback without canceling in-flight ASR", async () => {
    let resolve!: (value: { transcript: string; language: string; durationSeconds: number }) => void;
    mockTranscribe.mockReturnValue(new Promise((done) => { resolve = done; }));
    const first = vi.fn();
    const second = vi.fn();
    const view = renderInput(first);
    recorderState = { ...recorderState, state: "stopped", blob: new Blob(["voice"]) };
    view.rerender(<VoiceSteeringInput {...view.props} />);
    await waitFor(() => expect(mockTranscribe).toHaveBeenCalledOnce());
    view.rerender(<VoiceSteeringInput {...view.props} onTranscript={second} />);

    resolve({ transcript: "latest callback", language: "en", durationSeconds: 2 });

    await waitFor(() => expect(second).toHaveBeenCalledWith("latest callback"));
    expect(first).not.toHaveBeenCalled();
    expect(mockTranscribe).toHaveBeenCalledOnce();
  });

  it("discards voice provenance without deleting reviewed editor text", () => {
    const onDiscardTranscript = vi.fn();
    render(
      <VoiceSteeringInput
        value="corrected steer"
        rawTranscript="raw steer"
        disabled={false}
        onChange={vi.fn()}
        onTranscript={vi.fn()}
        onDiscardTranscript={onDiscardTranscript}
        onBusyChange={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Discard voice" }));

    expect(onDiscardTranscript).toHaveBeenCalledOnce();
    expect((screen.getByLabelText("Steering prompt") as HTMLTextAreaElement).value).toBe("corrected steer");
  });

  it("announces active recording to assistive technology", () => {
    recorderState = { ...recorderState, state: "recording" };
    renderInput();

    expect(screen.getByRole("status").textContent).toContain("Recording voice steering");
  });

  it("reports busy while recording and clears it after transcription", async () => {
    mockTranscribe.mockResolvedValue({ transcript: "deepen chapter 2", language: "en", durationSeconds: 2 });
    const onBusyChange = vi.fn();
    const props = {
      value: "typed steer",
      rawTranscript: null,
      disabled: false,
      onChange: vi.fn(),
      onTranscript: vi.fn(),
      onDiscardTranscript: vi.fn(),
      onBusyChange,
    };
    recorderState = { ...recorderState, state: "recording" };
    const view = render(<VoiceSteeringInput {...props} />);
    await waitFor(() => expect(onBusyChange).toHaveBeenLastCalledWith(true));

    recorderState = { ...recorderState, state: "stopped", blob: new Blob(["voice"]) };
    view.rerender(<VoiceSteeringInput {...props} />);

    await waitFor(() => expect(props.onTranscript).toHaveBeenCalled());
    await waitFor(() => expect(onBusyChange).toHaveBeenLastCalledWith(false));
  });
});
