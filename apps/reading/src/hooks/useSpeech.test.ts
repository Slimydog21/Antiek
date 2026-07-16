import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import { useSpeech } from "./useSpeech";

vi.mock("../lib/api", () => ({
  API_BASE: "http://antiek.test",
  apiFetch: vi.fn(),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function response(blob: Blob = new Blob(["audio"])) {
  return {
    ok: true,
    status: 200,
    blob: vi.fn().mockResolvedValue(blob),
  } as unknown as Response;
}

class FakeAudio {
  static instances: FakeAudio[] = [];
  static nextPlayPromises: Promise<void>[] = [];
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  pause = vi.fn();
  play = vi.fn<() => Promise<void>>(() =>
    FakeAudio.nextPlayPromises.shift() ?? Promise.resolve(),
  );

  constructor(readonly src: string) {
    FakeAudio.instances.push(this);
  }
}

describe("useSpeech", () => {
  const fetchMock = vi.mocked(apiFetch);
  const createObjectURL = vi.fn(
    (_blob: Blob) => `blob:spoken-reply-${createObjectURL.mock.calls.length}`,
  );
  const revokeObjectURL = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    FakeAudio.instances = [];
    FakeAudio.nextPlayPromises = [];
    vi.stubGlobal("Audio", FakeAudio);
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    createObjectURL.mockClear();
    revokeObjectURL.mockClear();
  });

  afterEach(() => vi.unstubAllGlobals());

  it("notifies exactly once after initial playback succeeds", async () => {
    fetchMock.mockResolvedValue(response());
    const onPlaybackStarted = vi.fn();
    const hook = renderHook(() => useSpeech({ onPlaybackStarted }));

    await act(() => hook.result.current.speak("Read this"));

    expect(hook.result.current.state).toBe("playing");
    expect(onPlaybackStarted).toHaveBeenCalledTimes(1);
    expect(FakeAudio.instances[0].play).toHaveBeenCalledTimes(1);
  });

  it("does not notify when playback rejects", async () => {
    fetchMock.mockResolvedValue(response());
    const onPlaybackStarted = vi.fn();
    const hook = renderHook(() => useSpeech({ onPlaybackStarted }));
    const failure = new Error("autoplay denied");
    FakeAudio.nextPlayPromises.push(Promise.reject(failure));

    await act(() => hook.result.current.speak("Read this"));

    expect(hook.result.current.state).toBe("error");
    expect(hook.result.current.error).toBe("autoplay denied");
    expect(onPlaybackStarted).not.toHaveBeenCalled();
    expect(FakeAudio.instances[0].pause).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:spoken-reply-1");
  });

  it("stop invalidates a request without resurrecting state", async () => {
    const pending = deferred<Response>();
    fetchMock.mockReturnValue(pending.promise);
    const onPlaybackStarted = vi.fn();
    const hook = renderHook(() => useSpeech({ onPlaybackStarted }));

    let speaking!: Promise<void>;
    act(() => {
      speaking = hook.result.current.speak("Read this");
    });
    act(() => hook.result.current.stop());
    pending.resolve(response());
    await act(() => speaking);

    expect(hook.result.current.state).toBe("idle");
    expect(FakeAudio.instances).toHaveLength(0);
    expect(onPlaybackStarted).not.toHaveBeenCalled();
  });

  it("whitespace supersedes playback into a clean idle state", async () => {
    fetchMock.mockResolvedValue(response());
    const hook = renderHook(() => useSpeech({ onPlaybackStarted: vi.fn() }));
    await act(() => hook.result.current.speak("Read this"));

    await act(() => hook.result.current.speak("   "));

    expect(hook.result.current.state).toBe("idle");
    expect(hook.result.current.error).toBeNull();
    expect(FakeAudio.instances[0].pause).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:spoken-reply-1");
  });

  it("a superseded response cannot replace or notify after the newer playback", async () => {
    const first = deferred<Response>();
    fetchMock.mockReturnValueOnce(first.promise).mockResolvedValueOnce(response());
    const onPlaybackStarted = vi.fn();
    const hook = renderHook(() => useSpeech({ onPlaybackStarted }));

    let oldSpeaking!: Promise<void>;
    act(() => {
      oldSpeaking = hook.result.current.speak("Old reply");
    });
    await act(() => hook.result.current.speak("New reply"));
    first.resolve(response());
    await act(() => oldSpeaking);

    expect(FakeAudio.instances).toHaveLength(1);
    expect(hook.result.current.state).toBe("playing");
    expect(onPlaybackStarted).toHaveBeenCalledTimes(1);
  });

  it("stop while play is pending prevents late playback truth", async () => {
    fetchMock.mockResolvedValue(response());
    const play = deferred<void>();
    FakeAudio.nextPlayPromises.push(play.promise);
    const onPlaybackStarted = vi.fn();
    const hook = renderHook(() => useSpeech({ onPlaybackStarted }));
    let speaking!: Promise<void>;

    act(() => {
      speaking = hook.result.current.speak("Read this");
    });
    await vi.waitFor(() => expect(FakeAudio.instances).toHaveLength(1));
    act(() => hook.result.current.stop());
    play.resolve();
    await act(() => speaking);

    expect(hook.result.current.state).toBe("idle");
    expect(FakeAudio.instances[0].pause).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:spoken-reply-1");
    expect(onPlaybackStarted).not.toHaveBeenCalled();
  });

  it("releases media on natural completion and playback error", async () => {
    fetchMock.mockResolvedValue(response());
    const hook = renderHook(() => useSpeech({ onPlaybackStarted: vi.fn() }));
    await act(() => hook.result.current.speak("First"));
    const first = FakeAudio.instances[0];

    act(() => first.onended?.());

    expect(hook.result.current.state).toBe("idle");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:spoken-reply-1");

    await act(() => hook.result.current.speak("Second"));
    const second = FakeAudio.instances[1];
    act(() => second.onerror?.());

    expect(hook.result.current.state).toBe("error");
    expect(hook.result.current.error).toBe("Playback failed.");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:spoken-reply-2");
  });

  it("unmount releases media allocated before play settles", async () => {
    fetchMock.mockResolvedValue(response());
    const play = deferred<void>();
    FakeAudio.nextPlayPromises.push(play.promise);
    const hook = renderHook(() => useSpeech({ onPlaybackStarted: vi.fn() }));
    let speaking!: Promise<void>;
    act(() => {
      speaking = hook.result.current.speak("Read this");
    });
    await vi.waitFor(() => expect(FakeAudio.instances).toHaveLength(1));

    hook.unmount();
    play.resolve();
    await act(() => speaking);

    expect(FakeAudio.instances[0].pause).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:spoken-reply-1");
  });

  it("unmount suppresses a late response and observer failures never own state", async () => {
    fetchMock.mockResolvedValueOnce(response());
    const observer = vi.fn(() => {
      throw new Error("animation unavailable");
    });
    const firstHook = renderHook(() => useSpeech({ onPlaybackStarted: observer }));
    await act(() => firstHook.result.current.speak("Read this"));
    expect(firstHook.result.current.state).toBe("playing");

    const pending = deferred<Response>();
    fetchMock.mockReturnValueOnce(pending.promise);
    const lateObserver = vi.fn();
    const secondHook = renderHook(() =>
      useSpeech({ onPlaybackStarted: lateObserver }),
    );
    let speaking!: Promise<void>;
    act(() => {
      speaking = secondHook.result.current.speak("Later");
    });
    secondHook.unmount();
    pending.resolve(response());
    await act(() => speaking);

    expect(observer).toHaveBeenCalledTimes(1);
    expect(lateObserver).not.toHaveBeenCalled();
  });
});
