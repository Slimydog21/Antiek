import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import InterviewVoiceCapture from "./InterviewVoiceCapture";

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn(),
}));

const apiFetchMock = vi.mocked(apiFetch);
const stopTrack = vi.fn();

class FakeMediaRecorder {
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(_stream: MediaStream, _options?: MediaRecorderOptions) {}

  start() {}

  stop() {
    this.ondataavailable?.({ data: new Blob(["audio"], { type: "audio/webm" }) });
  }
}

beforeEach(() => {
  apiFetchMock.mockReset();
  stopTrack.mockReset();
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: vi.fn().mockResolvedValue({
        getTracks: () => [{ stop: stopTrack }],
      }),
    },
  });
  Object.defineProperty(window, "MediaRecorder", {
    configurable: true,
    value: FakeMediaRecorder,
  });
  Object.defineProperty(globalThis, "MediaRecorder", {
    configurable: true,
    value: FakeMediaRecorder,
  });
  Object.defineProperty(window, "requestAnimationFrame", {
    configurable: true,
    value: (cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    },
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function recordAndUpload() {
  fireEvent.click(screen.getByRole("button", { name: "Grant mic access" }));
  fireEvent.click(await screen.findByRole("button", { name: "Start recording" }));
  fireEvent.click(screen.getByRole("button", { name: "Stop & upload" }));
}

describe("InterviewVoiceCapture", () => {
  it("sanitizes successful upload payloads before notifying the host", async () => {
    const onUploaded = vi.fn();
    apiFetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ audio_url: { href: "https://cdn.example/audio.webm" } }),
    } as Response);

    render(<InterviewVoiceCapture sessionId="int-1" onUploaded={onUploaded} />);

    await recordAndUpload();

    await screen.findByText(/Upload complete/i);
    expect(onUploaded).toHaveBeenCalledWith("");
    expect(typeof onUploaded.mock.calls[0]?.[0]).toBe("string");
    expect(stopTrack).toHaveBeenCalled();
  });

  it.each(["javascript:alert(1)", "data:text/html,owned", "/relative/audio.webm"])(
    "does not pass unsafe audio_url values to the host: %s",
    async (audio_url) => {
      const onUploaded = vi.fn();
      apiFetchMock.mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ audio_url, transcript: " invite transcript " }),
      } as Response);

      render(<InterviewVoiceCapture sessionId="int-1" onUploaded={onUploaded} />);

      await recordAndUpload();

      await screen.findByText(/Upload complete/i);
      expect(onUploaded).toHaveBeenCalledWith("invite transcript");
      expect(onUploaded).not.toHaveBeenCalledWith(audio_url);
      expect(stopTrack).toHaveBeenCalled();
    },
  );

  it("trims and passes safe uploaded audio URLs to the host", async () => {
    const onUploaded = vi.fn();
    apiFetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ audio_url: " https://cdn.example/audio.webm " }),
    } as Response);

    render(<InterviewVoiceCapture sessionId="int-1" onUploaded={onUploaded} />);

    await recordAndUpload();

    await screen.findByText(/Upload complete/i);
    expect(onUploaded).toHaveBeenCalledWith("https://cdn.example/audio.webm");
  });

  it("keeps malformed upload error detail out of host callbacks", async () => {
    const onUploadError = vi.fn();
    apiFetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: { code: "provider_missing" } }),
    } as Response);

    render(
      <InterviewVoiceCapture
        sessionId="int-1"
        onUploadError={onUploadError}
      />,
    );

    await recordAndUpload();

    await waitFor(() => expect(onUploadError).toHaveBeenCalledWith(503, "HTTP 503"));
    expect(await screen.findByText("Upload failed: HTTP 503")).toBeTruthy();
    expect(document.body.textContent).not.toContain("[object Object]");
  });

  it("sanitizes nested upload error messages for host callbacks", async () => {
    const onUploadError = vi.fn();
    apiFetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: { message: "  provider missing  " } }),
    } as Response);

    render(
      <InterviewVoiceCapture
        sessionId="int-1"
        onUploadError={onUploadError}
      />,
    );

    await recordAndUpload();

    await waitFor(() =>
      expect(onUploadError).toHaveBeenCalledWith(503, "provider missing"),
    );
    expect(await screen.findByText("Upload failed: provider missing")).toBeTruthy();
    expect(document.body.textContent).not.toContain("[object Object]");
  });
});
