import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useVoiceCapture } from "./useVoiceCapture";

// The actual recorder and capture hooks run; only native device APIs and HTTP
// are controlled. onstop arrives asynchronously, as MediaRecorder specifies.
const stopTrack = vi.fn();
class AsyncMediaRecorder {
  state = "inactive";
  mimeType = "audio/webm";
  ondataavailable: ((event: BlobEvent) => void) | null = null;
  onstop: ((event: Event) => void) | null = null;
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    setTimeout(() => {
      this.ondataavailable?.({ data: new Blob(["recorded audio"], { type: this.mimeType }) } as BlobEvent);
      this.onstop?.(new Event("stop"));
    }, 1);
  }
}
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
function installDeviceReplies() {
  stopTrack.mockClear();
  vi.useFakeTimers();
  vi.stubGlobal("MediaRecorder", AsyncMediaRecorder);
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: stopTrack }] })) } });
  const requests: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input) => {
    const path = new URL(String(input), "http://localhost").pathname; requests.push(path);
    return new Response(JSON.stringify(path === "/voice/transcribe"
      ? { transcript: "Recorded thought", language: "en", duration_seconds: 1 }
      : { event_id: "recorder-ack" }), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
  return requests;
}
it("an actual asynchronous recorder onstop reaches ASR without reusing the preceding recording", async () => {
  const requests = installDeviceReplies();
  const { result } = renderHook(() => useVoiceCapture());
  await act(async () => { await result.current.start(); });
  expect(result.current.recorderState).toBe("recording");
  let operation: ReturnType<typeof result.current.stopAndCapture> = Promise.resolve(null);
  act(() => { operation = result.current.stopAndCapture({ investigationId: "inv", canDispatch: () => true }); });
  // Commit the onstop state before advancing the polling loop.
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(result.current.recorderState).toBe("stopped");
  await act(async () => { await vi.advanceTimersByTimeAsync(5020); });
  let capture: Awaited<typeof operation> = null;
  await act(async () => { capture = await operation; });
  expect(requests).toEqual(["/voice/transcribe", "/events/typed"]);
  expect(capture).toEqual(expect.objectContaining({ transcript: "Recorded thought", eventId: "recorder-ack", sourceKind: "user" }));
  expect(stopTrack).toHaveBeenCalledOnce();

  await act(async () => { await result.current.start(); });
  act(() => { operation = result.current.stopAndCapture({ investigationId: "inv", canDispatch: () => true }); });
  await act(async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); });
  expect(requests).toEqual(["/voice/transcribe", "/events/typed"]);
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  await act(async () => { await vi.advanceTimersByTimeAsync(20); capture = await operation; });
  expect(requests).toEqual(["/voice/transcribe", "/events/typed", "/voice/transcribe", "/events/typed"]);
  expect(capture).toEqual(expect.objectContaining({ eventId: "recorder-ack", sourceKind: "user" }));
  expect(stopTrack).toHaveBeenCalledTimes(2);
});

it("actual recorder completion does not admit ASR into a revoked destination", async () => {
  const requests = installDeviceReplies();
  let admitted = true;
  const { result } = renderHook(() => useVoiceCapture());
  await act(async () => { await result.current.start(); });
  let operation: ReturnType<typeof result.current.stopAndCapture> = Promise.resolve(null);
  act(() => { operation = result.current.stopAndCapture({ investigationId: "inv", canDispatch: () => admitted }); });
  admitted = false;
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(result.current.recorderState).toBe("stopped");
  let capture: Awaited<typeof operation> = null;
  await act(async () => { await vi.advanceTimersByTimeAsync(20); capture = await operation; });
  expect(capture).toBeNull();
  expect(requests).toEqual([]);
  expect(result.current.phase).toBe("error");
  expect(stopTrack).toHaveBeenCalledOnce();
});
