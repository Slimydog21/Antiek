import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

/**
 * VoiceToDraft.test — speak an idea into the draft, user-sourced (SPR-09 M4).
 *
 * Mechanically checked:
 *  - a successful capture persists a USER-AUTHORED block (provenance_kind
 *    "user_authored", NO node_id) — §9: the writer's own speech, never model
 *    output;
 *  - rigor #3c — a transcription failure persists NOTHING and surfaces the
 *    error (no silent drop, no mislabel);
 *  - a blank (silent) transcript is flagged, not invented.
 */

const { useVoiceCaptureMock, placeBlockMock } = vi.hoisted(() => ({
  useVoiceCaptureMock: vi.fn(),
  placeBlockMock: vi.fn(),
}));

vi.mock("../../hooks/useVoiceCapture", () => ({
  useVoiceCapture: useVoiceCaptureMock,
}));
vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  placeBlock: placeBlockMock,
}));

import VoiceToDraft from "./VoiceToDraft";

function voiceState(over: Record<string, unknown> = {}) {
  return {
    phase: "recording",
    error: null,
    recorderState: "recording",
    result: null,
    start: vi.fn(),
    stopAndCapture: vi.fn(),
    reset: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  placeBlockMock.mockReset().mockResolvedValue("oblk-voice");
  useVoiceCaptureMock.mockReset();
});
afterEach(cleanup);

function renderVtd() {
  return render(
    <VoiceToDraft
      sectionId="sec-1"
      deliverableId="dlv-1"
      investigationId="inv-1"
      blockIndex={0}
      onDrafted={vi.fn()}
    />,
  );
}

describe("VoiceToDraft — user-sourced spoken draft", () => {
  it("persists a USER-AUTHORED block on a good transcript (§9, never model output)", async () => {
    const stopAndCapture = vi.fn().mockResolvedValue({
      transcript: "the thing I want to argue", transcriptStatus: "ok",
      sourceKind: "user", language: "en", durationSeconds: 3, eventId: "ev-1",
    });
    useVoiceCaptureMock.mockReturnValue(voiceState({ stopAndCapture }));
    renderVtd();
    await userEvent.click(screen.getByRole("button", { name: /stop & add/i }));
    await waitFor(() =>
      expect(placeBlockMock).toHaveBeenCalledWith(
        expect.objectContaining({
          block_kind: "user_authored",
          provenance_kind: "user_authored",
          content: "the thing I want to argue",
        }),
      ),
    );
    // §9: a user-authored block carries NO node_id (no fabricated citation).
    expect(placeBlockMock.mock.calls[0][0].node_id).toBeUndefined();
  });

  it("rigor #3c — a transcription failure persists NOTHING and surfaces it", async () => {
    // stopAndCapture returns null on failure + sets voice.error (the hook's
    // contract); the draft must not be silently dropped or mislabelled.
    const stopAndCapture = vi.fn().mockResolvedValue(null);
    useVoiceCaptureMock.mockReturnValue(
      voiceState({ stopAndCapture, error: "Transcription service unavailable." }),
    );
    renderVtd();
    await userEvent.click(screen.getByRole("button", { name: /stop & add/i }));
    await waitFor(() => expect(screen.getByText(/transcription service unavailable/i)).toBeTruthy());
    expect(placeBlockMock).not.toHaveBeenCalled();
  });

  it("a blank (silent) transcript is flagged, not invented", async () => {
    const stopAndCapture = vi.fn().mockResolvedValue({
      transcript: "", transcriptStatus: "empty", sourceKind: "user",
      language: null, durationSeconds: 1, eventId: "ev-2",
    });
    useVoiceCaptureMock.mockReturnValue(voiceState({ stopAndCapture }));
    renderVtd();
    await userEvent.click(screen.getByRole("button", { name: /stop & add/i }));
    await waitFor(() => expect(screen.getByText(/didn't catch any words/i)).toBeTruthy());
    expect(placeBlockMock).not.toHaveBeenCalled();
  });

  it("keeps a spoken block saved when the outline refresh rejects", async () => {
    useVoiceCaptureMock.mockReturnValue(voiceState({
      stopAndCapture: vi.fn().mockResolvedValue({
        transcript: "a committed thought", transcriptStatus: "ok", sourceKind: "user",
        language: "en", durationSeconds: 2, eventId: "ev-3",
      }),
    }));
    render(
      <VoiceToDraft
        sectionId="sec-1" deliverableId="dlv-1" investigationId="inv-1" blockIndex={0}
        onDrafted={vi.fn().mockRejectedValue(new Error("refresh offline"))}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /stop & add/i }));
    await waitFor(() => expect(screen.getByText(/added.*user-sourced/i)).toBeTruthy());
    expect(screen.queryByText(/couldn't save/i)).toBeNull();
    expect(placeBlockMock).toHaveBeenCalledTimes(1);
  });
});
