import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useVoiceRecorder } from "./useVoiceRecorder";

const originalMediaDevices = Object.getOwnPropertyDescriptor(navigator, "mediaDevices");
const originalMediaRecorder = Object.getOwnPropertyDescriptor(globalThis, "MediaRecorder");

afterEach(() => {
  vi.restoreAllMocks();
  if (originalMediaDevices) Object.defineProperty(navigator, "mediaDevices", originalMediaDevices);
  else delete (navigator as { mediaDevices?: MediaDevices }).mediaDevices;
  if (originalMediaRecorder) Object.defineProperty(globalThis, "MediaRecorder", originalMediaRecorder);
  else delete (globalThis as { MediaRecorder?: typeof MediaRecorder }).MediaRecorder;
});

describe("useVoiceRecorder lifecycle", () => {
  it("emits one listening beat only after MediaRecorder starts", async () => {
    const stream = { getTracks: () => [] } as unknown as MediaStream;
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    });
    const startRecorder = vi.fn();
    class FakeMediaRecorder {
      state: RecordingState = "inactive";
      mimeType = "audio/webm";
      ondataavailable: ((event: BlobEvent) => void) | null = null;
      onstop: (() => void) | null = null;
      start = startRecorder.mockImplementation(() => {
        this.state = "recording";
      });
      stop = vi.fn();
      constructor(_stream: MediaStream) {}
    }
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
    const onRecordingStarted = vi.fn();
    const hook = renderHook(() =>
      useVoiceRecorder({ onRecordingStarted }),
    );

    await act(async () => {
      await hook.result.current.start();
    });

    expect(startRecorder).toHaveBeenCalledOnce();
    expect(onRecordingStarted).toHaveBeenCalledOnce();
    expect(hook.result.current.state).toBe("recording");
  });

  it("stays silent when MediaRecorder.start throws", async () => {
    const stopTrack = vi.fn();
    const stream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream;
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    });
    class FailingMediaRecorder {
      state: RecordingState = "inactive";
      mimeType = "audio/webm";
      ondataavailable: ((event: BlobEvent) => void) | null = null;
      onstop: (() => void) | null = null;
      start = vi.fn(() => {
        throw new Error("recorder hardware unavailable");
      });
      stop = vi.fn();
      constructor(_stream: MediaStream) {}
    }
    vi.stubGlobal("MediaRecorder", FailingMediaRecorder);
    const onRecordingStarted = vi.fn();
    const hook = renderHook(() =>
      useVoiceRecorder({ onRecordingStarted }),
    );

    await act(async () => {
      await hook.result.current.start();
    });

    expect(onRecordingStarted).not.toHaveBeenCalled();
    expect(hook.result.current.state).toBe("error");
    expect(hook.result.current.error).toBe("recorder hardware unavailable");
    expect(stopTrack).toHaveBeenCalledOnce();
  });

  it("stays silent when MediaRecorder construction fails", async () => {
    const stopTrack = vi.fn();
    const stream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream;
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    });
    class FailingMediaRecorder {
      constructor(_stream: MediaStream) {
        throw new Error("recorder construction failed");
      }
    }
    vi.stubGlobal("MediaRecorder", FailingMediaRecorder);
    const onRecordingStarted = vi.fn();
    const hook = renderHook(() =>
      useVoiceRecorder({ onRecordingStarted }),
    );

    await act(async () => {
      await hook.result.current.start();
    });

    expect(onRecordingStarted).not.toHaveBeenCalled();
    expect(hook.result.current.state).toBe("error");
    expect(hook.result.current.error).toBe("recorder construction failed");
    expect(stopTrack).toHaveBeenCalledOnce();
  });

  it("keeps recording when the listening-beat observer throws", async () => {
    const stopTrack = vi.fn();
    const stream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream;
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    });
    class FakeMediaRecorder {
      state: RecordingState = "inactive";
      mimeType = "audio/webm";
      ondataavailable: ((event: BlobEvent) => void) | null = null;
      onstop: (() => void) | null = null;
      start = vi.fn(() => {
        this.state = "recording";
      });
      stop = vi.fn();
      constructor(_stream: MediaStream) {}
    }
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
    const onRecordingStarted = vi.fn(() => {
      throw new Error("choreography observer failed");
    });
    const hook = renderHook(() =>
      useVoiceRecorder({ onRecordingStarted }),
    );

    await act(async () => {
      await hook.result.current.start();
    });

    expect(onRecordingStarted).toHaveBeenCalledOnce();
    expect(hook.result.current.state).toBe("recording");
    expect(hook.result.current.error).toBeNull();
    expect(stopTrack).not.toHaveBeenCalled();
  });

  it("stays silent when microphone permission is denied", async () => {
    const denied = Object.assign(new Error("permission denied"), {
      name: "NotAllowedError",
    });
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockRejectedValue(denied) },
    });
    const mediaRecorder = vi.fn();
    vi.stubGlobal("MediaRecorder", mediaRecorder);
    const onRecordingStarted = vi.fn();
    const hook = renderHook(() =>
      useVoiceRecorder({ onRecordingStarted }),
    );

    await act(async () => {
      await hook.result.current.start();
    });

    expect(mediaRecorder).not.toHaveBeenCalled();
    expect(onRecordingStarted).not.toHaveBeenCalled();
    expect(hook.result.current.state).toBe("denied");
    expect(hook.result.current.error).toContain("permission was denied");
  });

  it("stops a late microphone stream when its owner unmounts during permission", async () => {
    const stopTrack = vi.fn();
    const stream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream;
    let resolvePermission!: (value: MediaStream) => void;
    const permission = new Promise<MediaStream>((resolve) => { resolvePermission = resolve; });
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockReturnValue(permission) },
    });
    const mediaRecorder = vi.fn();
    vi.stubGlobal("MediaRecorder", mediaRecorder);
    const onRecordingStarted = vi.fn();
    const hook = renderHook(() => useVoiceRecorder({ onRecordingStarted }));

    let start!: Promise<void>;
    act(() => { start = hook.result.current.start(); });
    hook.unmount();
    resolvePermission(stream);
    await act(async () => { await start; });

    expect(stopTrack).toHaveBeenCalledOnce();
    expect(mediaRecorder).not.toHaveBeenCalled();
    expect(onRecordingStarted).not.toHaveBeenCalled();
  });

  it("does not let a stale permission failure stop a newer recording", async () => {
    const stopNewTrack = vi.fn();
    const newStream = { getTracks: () => [{ stop: stopNewTrack }] } as unknown as MediaStream;
    let rejectFirst!: (reason: Error) => void;
    let resolveSecond!: (value: MediaStream) => void;
    const firstPermission = new Promise<MediaStream>((_resolve, reject) => { rejectFirst = reject; });
    const secondPermission = new Promise<MediaStream>((resolve) => { resolveSecond = resolve; });
    const getUserMedia = vi.fn()
      .mockReturnValueOnce(firstPermission)
      .mockReturnValueOnce(secondPermission);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia },
    });
    let recorder!: FakeMediaRecorder;
    class FakeMediaRecorder {
      state: RecordingState = "inactive";
      mimeType = "audio/webm";
      ondataavailable: ((event: BlobEvent) => void) | null = null;
      onstop: (() => void) | null = null;
      start = vi.fn(() => { this.state = "recording"; });
      stop = vi.fn(() => {
        this.state = "inactive";
        this.onstop?.();
      });

      constructor(_stream: MediaStream) {
        recorder = this;
      }
    }
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
    const onRecordingStarted = vi.fn();
    const hook = renderHook(() => useVoiceRecorder({ onRecordingStarted }));

    let first!: Promise<void>;
    let second!: Promise<void>;
    act(() => {
      first = hook.result.current.start();
      second = hook.result.current.start();
    });
    resolveSecond(newStream);
    await act(async () => { await second; });
    rejectFirst(new Error("stale permission failure"));
    await act(async () => { await first; });

    expect(recorder.start).toHaveBeenCalledOnce();
    expect(onRecordingStarted).toHaveBeenCalledOnce();
    expect(stopNewTrack).not.toHaveBeenCalled();
    hook.unmount();
    expect(stopNewTrack).toHaveBeenCalledOnce();
  });
});
