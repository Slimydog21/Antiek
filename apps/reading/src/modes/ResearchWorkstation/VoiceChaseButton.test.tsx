import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

/**
 * VoiceChaseButton — the M4 honest-no-key voice path (SPR-04). The
 * load-bearing branch is: transcription is gated on the operator OpenAI key,
 * so a 503 must surface the shared no-key failure (never a fabricated
 * transcript), and a success must hand the transcript up unchanged.
 */

// vi.mock factories are hoisted above imports, so anything they reference must
// be hoisted too (matches the CascadeProposal.test pattern).
const { transcribeAudioMock, FakeApiError, recorder } = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number;
    constructor(status: number) {
      super("api");
      this.status = status;
    }
  }
  return {
    transcribeAudioMock: vi.fn(),
    FakeApiError,
    // Already "stopped" with a blob, so the transcribe effect fires on mount.
    recorder: {
      state: "stopped" as const,
      blob: new Blob(["x"]),
      start: vi.fn(),
      stop: vi.fn(),
      reset: vi.fn(),
      error: null as string | null,
    },
  };
});

vi.mock("../../lib/api", () => ({
  transcribeAudio: (...args: unknown[]) => transcribeAudioMock(...args),
  ApiError: FakeApiError,
}));
vi.mock("../../hooks/useVoiceRecorder", () => ({ useVoiceRecorder: () => recorder }));

import VoiceChaseButton from "./VoiceChaseButton";

beforeEach(() => {
  transcribeAudioMock.mockReset();
  recorder.reset.mockReset();
});

describe("VoiceChaseButton — M4 honest no-key voice chase", () => {
  it("a 503 (no provider key) shows the honest no-key failure and hands up no transcript", async () => {
    transcribeAudioMock.mockRejectedValue(new FakeApiError(503));
    const onTranscript = vi.fn();
    render(<VoiceChaseButton onTranscript={onTranscript} />);
    expect(await screen.findByText(/model provider/i)).toBeTruthy();
    expect(onTranscript).not.toHaveBeenCalled();
  });

  it("a successful transcription hands the transcript up unchanged", async () => {
    transcribeAudioMock.mockResolvedValue({ transcript: "why does X cause Y" });
    const onTranscript = vi.fn();
    render(<VoiceChaseButton onTranscript={onTranscript} />);
    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith("why does X cause Y"));
  });
});
