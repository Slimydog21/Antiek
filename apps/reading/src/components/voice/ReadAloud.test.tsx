/**
 * ReadAloud.test.tsx — SPR-14 M2 + M3-voice-out.
 *
 * The shared control's play/pause/stop machine + the §9.0 honest-withheld state.
 * We mock at the lib/api network boundary (apiFetch + getChunk) and let the REAL
 * `narrate` run, so the control test exercises the real §9.0 ordering + the real
 * rejection path — not a re-stubbed `narrate`. (A spy that RETURNS a rejected
 * promise trips vitest v4's unhandled-rejection tracker before the component's
 * await attaches; mocking the leaf network calls and keeping `narrate` real
 * avoids that and is the more faithful test.)
 *
 * The audio element is a fake (jsdom does not implement HTMLMediaElement.play /
 * pause) injected via `makeAudio`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";

import ReadAloud from "./ReadAloud";

// Mock the lib/api boundary that the REAL `narrate` calls through: apiFetch (the
// /speech/tts synthesis) + getChunk (the §9.0 servability lookup). narrate,
// assertServable, and the length scoping all run for real.
vi.mock("../../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
  getChunk: vi.fn(),
}));

import { apiFetch, getChunk } from "../../lib/api";
const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;
const mockGetChunk = getChunk as unknown as ReturnType<typeof vi.fn>;

// A fake audio element: play/pause are jsdom-unimplemented, so we record calls.
function makeFakeAudio() {
  const audio = {
    play: vi.fn().mockResolvedValue(undefined),
    pause: vi.fn(),
    onended: null as (() => void) | null,
    onerror: null as (() => void) | null,
  };
  return audio as unknown as HTMLAudioElement & {
    play: ReturnType<typeof vi.fn>;
    pause: ReturnType<typeof vi.fn>;
  };
}

const AUDIO_FIXTURE = new Blob([new Uint8Array([1, 2, 3])], { type: "audio/mpeg" });

function okAudioResponse(): Response {
  return { ok: true, status: 200, blob: async () => AUDIO_FIXTURE } as unknown as Response;
}

beforeEach(() => {
  mockFetch.mockReset();
  mockGetChunk.mockReset();
});
afterEach(cleanup);

describe("ReadAloud control", () => {
  it("plays for given text: clicking Read aloud synthesizes + plays the audio", async () => {
    mockFetch.mockResolvedValue(okAudioResponse());
    const fake = makeFakeAudio();
    const onPlaybackStarted = vi.fn();

    const { getByRole } = render(
      <ReadAloud
        text="a model sentence"
        makeAudio={() => fake}
        onPlaybackStarted={onPlaybackStarted}
      />,
    );

    await act(async () => {
      fireEvent.click(getByRole("button", { name: "Read aloud" }));
    });

    await waitFor(() => expect(fake.play).toHaveBeenCalledTimes(1));
    // The text reached the synthesis call.
    expect(JSON.parse(mockFetch.mock.calls[0][1]?.body as string).text).toBe(
      "a model sentence",
    );
    // Now playing → control offers Pause + Stop.
    expect(getByRole("button", { name: "Pause" })).toBeTruthy();
    expect(getByRole("button", { name: "Stop" })).toBeTruthy();
    expect(onPlaybackStarted).toHaveBeenCalledOnce();
  });

  it("LOAD-BEARING §9.0: a withheld chunk surfaces the honest 'withheld' state, distinct from error, and the synthesis call never fires", async () => {
    // servable === false ⇒ the real narrate refuses before any synthesis.
    mockGetChunk.mockResolvedValue({ chunk_id: "c1", servable: false } as never);
    const fake = makeFakeAudio();

    const { getByRole, container } = render(
      <ReadAloud text="withheld body" chunkId="c1" makeAudio={() => fake} />,
    );

    fireEvent.click(getByRole("button", { name: "Read aloud" }));

    await waitFor(() =>
      expect(container.querySelector(".read-aloud")?.getAttribute("data-state")).toBe(
        "withheld",
      ),
    );
    // Honest, distinct copy — a status, not a generic error.
    expect(container.querySelector(".read-aloud__withheld")).toBeTruthy();
    expect(container.querySelector(".read-aloud__error")).toBeNull();
    // The §9.0 body never reached the synthesis service, and nothing played.
    expect(mockFetch).not.toHaveBeenCalled();
    expect(fake.play).not.toHaveBeenCalled();
  });

  it("empty text is a quiet no-op: nothing is synthesized, no crash", async () => {
    const fake = makeFakeAudio();
    const { getByRole } = render(<ReadAloud text="   " makeAudio={() => fake} />);

    fireEvent.click(getByRole("button", { name: "Read aloud" }));
    // Give any (absent) async work a tick.
    await act(async () => { await Promise.resolve(); });

    expect(mockFetch).not.toHaveBeenCalled();
    expect(fake.play).not.toHaveBeenCalled();
  });

  it("pause pauses the playing audio without re-synthesizing", async () => {
    mockFetch.mockResolvedValue(okAudioResponse());
    const fake = makeFakeAudio();
    const onPlaybackStarted = vi.fn();

    const { getByRole } = render(
      <ReadAloud
        text="x"
        makeAudio={() => fake}
        onPlaybackStarted={onPlaybackStarted}
      />,
    );

    await act(async () => {
      fireEvent.click(getByRole("button", { name: "Read aloud" }));
    });
    await waitFor(() => expect(fake.play).toHaveBeenCalledTimes(1));

    await act(async () => {
      fireEvent.click(getByRole("button", { name: "Pause" }));
    });
    expect(fake.pause).toHaveBeenCalled();

    // Resume re-uses the same audio (only one synthesis total).
    await act(async () => {
      fireEvent.click(getByRole("button", { name: "Resume" }));
    });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(fake.play).toHaveBeenCalledTimes(2);
    expect(onPlaybackStarted).toHaveBeenCalledOnce();
  });

  it("does not resurrect playing state when Stop wins a pending resume", async () => {
    mockFetch.mockResolvedValue(okAudioResponse());
    let resolveResume!: () => void;
    const fake = makeFakeAudio();
    fake.play
      .mockResolvedValueOnce(undefined)
      .mockReturnValueOnce(new Promise<void>((resolve) => { resolveResume = resolve; }));
    const onPlaybackStarted = vi.fn();
    const { getByRole, container } = render(
      <ReadAloud text="x" makeAudio={() => fake} onPlaybackStarted={onPlaybackStarted} />,
    );
    fireEvent.click(getByRole("button", { name: "Read aloud" }));
    await waitFor(() => expect(getByRole("button", { name: "Pause" })).toBeTruthy());
    fireEvent.click(getByRole("button", { name: "Pause" }));
    fireEvent.click(getByRole("button", { name: "Resume" }));
    fireEvent.click(getByRole("button", { name: "Stop" }));

    await act(async () => { resolveResume(); });

    expect(container.querySelector(".read-aloud")?.getAttribute("data-state")).toBe("idle");
    expect(onPlaybackStarted).toHaveBeenCalledOnce();
  });

  it("does not update state after unmount wins a pending resume", async () => {
    mockFetch.mockResolvedValue(okAudioResponse());
    let resolveResume!: () => void;
    const fake = makeFakeAudio();
    fake.play
      .mockResolvedValueOnce(undefined)
      .mockReturnValueOnce(new Promise<void>((resolve) => { resolveResume = resolve; }));
    const onPlaybackStarted = vi.fn();
    const view = render(
      <ReadAloud text="x" makeAudio={() => fake} onPlaybackStarted={onPlaybackStarted} />,
    );
    fireEvent.click(view.getByRole("button", { name: "Read aloud" }));
    await waitFor(() => expect(view.getByRole("button", { name: "Pause" })).toBeTruthy());
    fireEvent.click(view.getByRole("button", { name: "Pause" }));
    fireEvent.click(view.getByRole("button", { name: "Resume" }));
    view.unmount();

    await act(async () => { resolveResume(); });

    expect(onPlaybackStarted).toHaveBeenCalledOnce();
    expect(fake.pause).toHaveBeenCalledTimes(2);
  });

  it("does not announce playback when audio.play rejects", async () => {
    mockFetch.mockResolvedValue(okAudioResponse());
    const fake = makeFakeAudio();
    fake.play.mockRejectedValue(new Error("autoplay blocked"));
    const onPlaybackStarted = vi.fn();
    const { getByRole, container } = render(
      <ReadAloud text="x" makeAudio={() => fake} onPlaybackStarted={onPlaybackStarted} />,
    );

    fireEvent.click(getByRole("button", { name: "Read aloud" }));

    await waitFor(() =>
      expect(container.querySelector(".read-aloud")?.getAttribute("data-state")).toBe("error"),
    );
    expect(onPlaybackStarted).not.toHaveBeenCalled();
  });

  it("does not create audio or announce playback after unmount during synthesis", async () => {
    let resolveResponse!: (response: Response) => void;
    mockFetch.mockReturnValue(new Promise<Response>((resolve) => {
      resolveResponse = resolve;
    }));
    const fake = makeFakeAudio();
    const makeAudio = vi.fn(() => fake);
    const onPlaybackStarted = vi.fn();
    const view = render(
      <ReadAloud text="x" makeAudio={makeAudio} onPlaybackStarted={onPlaybackStarted} />,
    );
    fireEvent.click(view.getByRole("button", { name: "Read aloud" }));
    view.unmount();

    await act(async () => {
      resolveResponse(okAudioResponse());
      await Promise.resolve();
    });

    expect(makeAudio).not.toHaveBeenCalled();
    expect(onPlaybackStarted).not.toHaveBeenCalled();
  });

  it("keeps playing when the playback observer throws", async () => {
    mockFetch.mockResolvedValue(okAudioResponse());
    const fake = makeFakeAudio();
    const { getByRole, container } = render(
      <ReadAloud
        text="x"
        makeAudio={() => fake}
        onPlaybackStarted={() => { throw new Error("observer failed"); }}
      />,
    );

    fireEvent.click(getByRole("button", { name: "Read aloud" }));

    await waitFor(() =>
      expect(container.querySelector(".read-aloud")?.getAttribute("data-state")).toBe("playing"),
    );
    expect(fake.pause).not.toHaveBeenCalled();
  });

  it("PROVENANCE: the control carries the model-generated source-kind attribute (never user)", () => {
    const { container } = render(<ReadAloud text="model text" />);
    const el = container.querySelector(".read-aloud");
    expect(el?.getAttribute("data-source-kind")).toBe("ai");
    expect(el?.getAttribute("data-source-kind")).not.toBe("user");
  });

  it("a non-withheld failure (503 from the stubbed provider) surfaces the generic error state, distinct from withheld", async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 503 } as unknown as Response);
    const fake = makeFakeAudio();

    const { getByRole, container } = render(
      <ReadAloud text="some text" makeAudio={() => fake} />,
    );
    fireEvent.click(getByRole("button", { name: "Read aloud" }));
    await waitFor(() =>
      expect(container.querySelector(".read-aloud")?.getAttribute("data-state")).toBe("error"),
    );
    expect(container.querySelector(".read-aloud__error")).toBeTruthy();
    expect(container.querySelector(".read-aloud__withheld")).toBeNull();
  });
});
