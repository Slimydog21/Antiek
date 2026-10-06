import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", () => ({ apiFetch }));
import InterviewVoiceCapture from "./InterviewVoiceCapture";

let recorder: Recorder;
const stopTrack = vi.fn();
class Recorder {
  state = "inactive";
  mimeType = "audio/mp4";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  constructor() { recorder = this; }
  start() { this.state = "recording"; }
  stop() { this.state = "inactive"; }
}

beforeEach(() => {
  apiFetch.mockReset();
  stopTrack.mockReset();
  vi.stubGlobal("MediaRecorder", Recorder);
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => setTimeout(() => callback(0), 0));
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: {
    getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: stopTrack }] }),
  } });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

async function start(props: Parameters<typeof InterviewVoiceCapture>[0]) {
  const view = render(<InterviewVoiceCapture {...props} />);
  fireEvent.click(screen.getByRole("button", { name: /grant mic access/i }));
  fireEvent.click(await screen.findByRole("button", { name: /start recording/i }));
  return view;
}
function flush() {
  recorder.ondataavailable?.({ data: new Blob(["final recorded bytes"], { type: recorder.mimeType }) });
  recorder.onstop?.();
}

describe("Speak recording completion", () => {
  it("waits for the final data/stop events and sends the browser's actual audio format", async () => {
    const onUploaded = vi.fn();
    apiFetch.mockResolvedValue({ ok: true, json: async () => ({ transcript: "test response" }) });
    await start({ buildUploadUrl: () => "/speak/invite/test/voice", onUploaded });
    fireEvent.click(screen.getByRole("button", { name: /stop & upload/i }));
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
    expect(apiFetch).not.toHaveBeenCalled();
    act(flush);
    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith("test response"));
    const init: RequestInit = apiFetch.mock.calls[0][1];
    expect(init.body).toBeInstanceOf(Blob);
    expect(init.body instanceof Blob && init.body.size).toBe(20);
    expect(init.headers).toEqual({ "Content-Type": "audio/mp4" });
    expect(stopTrack).toHaveBeenCalledOnce();
  });

  it("refuses an empty recording without contacting the API", async () => {
    await start({ buildUploadUrl: () => "/speak/invite/test/voice" });
    fireEvent.click(screen.getByRole("button", { name: /stop & upload/i }));
    act(() => recorder.onstop?.());
    expect(await screen.findByText(/no audio captured/i)).toBeTruthy();
    expect(apiFetch).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /try recording again/i })).toBeTruthy();
  });

  it("does not signal completion for a success status with no recording result", async () => {
    const onUploaded = vi.fn();
    apiFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    await start({ buildUploadUrl: () => "/speak/invite/test/voice", onUploaded });
    fireEvent.click(screen.getByRole("button", { name: /stop & upload/i }));
    act(flush);
    expect(await screen.findByText(/didn't confirm your recording/i)).toBeTruthy();
    expect(onUploaded).not.toHaveBeenCalled();
  });

  it.each([401, 403, 503])("preserves HTTP %i refusal and offers a fresh recording, without completion", async (status) => {
    const onUploaded = vi.fn();
    const onUploadError = vi.fn();
    apiFetch.mockResolvedValue({ ok: false, status, json: async () => ({ detail: "transcription unavailable" }) });
    await start({ buildUploadUrl: () => "/speak/invite/test/voice", onUploaded, onUploadError });
    fireEvent.click(screen.getByRole("button", { name: /stop & upload/i }));
    act(flush);
    expect(await screen.findByText(/upload failed: transcription unavailable/i)).toBeTruthy();
    expect(onUploadError).toHaveBeenCalledWith(status, "transcription unavailable");
    expect(onUploaded).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /try recording again/i })).toBeTruthy();
  });

  it("releases the microphone if the browser cannot create a recorder", async () => {
    vi.stubGlobal("MediaRecorder", class { constructor() { throw new Error("Unsupported audio format"); } });
    await start({ buildUploadUrl: () => "/speak/invite/test/voice" });
    expect(await screen.findByText(/unsupported audio format/i)).toBeTruthy();
    expect(stopTrack).toHaveBeenCalledOnce();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("refuses a recorder that never completes within the finite flush deadline", async () => {
    await start({ buildUploadUrl: () => "/speak/invite/test/voice" });
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: /stop & upload/i }));
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(screen.getByText(/recording didn't finish/i)).toBeTruthy();
    expect(apiFetch).not.toHaveBeenCalled();
    expect(stopTrack).toHaveBeenCalledOnce();
  });

  it("stops a permission result that arrives after unmount", async () => {
    let resolve!: (value: unknown) => void;
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: {
      getUserMedia: vi.fn().mockReturnValue(new Promise((r) => { resolve = r; })),
    } });
    const view = render(<InterviewVoiceCapture buildUploadUrl={() => "/speak/invite/test/voice"} />);
    fireEvent.click(screen.getByRole("button", { name: /grant mic access/i }));
    view.unmount();
    await act(async () => resolve({ getTracks: () => [{ stop: stopTrack }] }));
    expect(stopTrack).toHaveBeenCalledOnce();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("never uploads a recorder flush after its owner unmounts", async () => {
    const view = await start({ buildUploadUrl: () => "/speak/invite/test/voice" });
    fireEvent.click(screen.getByRole("button", { name: /stop & upload/i }));
    view.unmount();
    act(flush);
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });
    expect(apiFetch).not.toHaveBeenCalled();
    expect(stopTrack).toHaveBeenCalledOnce();
  });
});
