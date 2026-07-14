import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MultimediaLocalAudiblePlayback } from "../../api/multimedia";
import { ActiveListeningPlayer } from "./ActiveListeningPlayer";

const playback: MultimediaLocalAudiblePlayback = {
  asset_id: "asset-1", revision_id: "revision-1", receipt_sha256: "a".repeat(64),
  audio_sha256: "b".repeat(64), audio_size_bytes: 10, duration_seconds: 45,
  chapter_ids: ["one", "two"],
  chapters: [
    { chapter_id: "one", title: "First principles", sequence: 0, start_offset_seconds: 0, end_offset_seconds: 20 },
    { chapter_id: "two", title: "The mechanism", sequence: 1, start_offset_seconds: 20, end_offset_seconds: 45 },
  ],
  retention_marker_count: 2, learned_claim_count: 1, source_count: 1,
  learned_claims: [{
    line_id: "two-line-0", chapter_id: "two", claim_text: "Lift changes with airflow.", source_count: 1,
    follow_up_prompt: "Recall the mechanism.", source_chunk_ids: ["chunk-1"], evidence_status: "verified_exact",
    evidence_sources: [{ chunk_id: "chunk-1", document_id: "doc-flight",
      locator: "Aerodynamics / Lift", authority_kind: "canonical_graph", chunk_sha256: "c".repeat(64),
      start_utf8_byte: 0, end_utf8_byte: 26, span_sha256: "d".repeat(64), exact_text: "Lift changes with airflow." }],
  }],
  audio_url: "/audio.wav",
};

const handlers = new Map<MediaSessionAction, MediaSessionActionHandler | null>();
const mediaSession = {
  metadata: null,
  playbackState: "none",
  setActionHandler: vi.fn((action: MediaSessionAction, handler: MediaSessionActionHandler | null) => handlers.set(action, handler)),
  setPositionState: vi.fn(),
};

beforeEach(() => {
  handlers.clear();
  vi.clearAllMocks();
  Object.defineProperty(navigator, "mediaSession", { configurable: true, value: mediaSession });
  Object.defineProperty(window, "MediaMetadata", { configurable: true, value: class { constructor(value: unknown) { Object.assign(this, value); } } });
});

afterEach(() => cleanup());

describe("ActiveListeningPlayer", () => {
  it("seeks chapters, clamps 15-second jumps, tracks time, and changes speed", () => {
    render(<ActiveListeningPlayer playback={playback} title="Flight lesson" />);
    const audio = screen.getByLabelText("Audio playback for Flight lesson") as HTMLAudioElement;
    fireEvent.click(screen.getByRole("button", { name: /The mechanism/ }));
    expect(audio.currentTime).toBe(20);
    fireEvent.timeUpdate(audio, { target: { currentTime: 44 } });
    expect(screen.getByRole("button", { name: /The mechanism/ }).getAttribute("aria-current")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Forward 15 seconds" }));
    expect(audio.currentTime).toBe(45);
    fireEvent.click(screen.getByRole("radio", { name: "1.5x" }));
    expect(audio.playbackRate).toBe(1.5);
    expect(screen.getByRole("radio", { name: "1.5x" }).getAttribute("aria-checked")).toBe("true");
  });

  it("groups exact learned claims under their verified chapter", () => {
    render(<ActiveListeningPlayer playback={playback} title="Flight lesson" />);
    fireEvent.click(screen.getByRole("button", { name: "Review learned claims" }));
    expect(screen.getByText("Lift changes with airflow.")).toBeTruthy();
    expect(screen.getByText(/Recall the mechanism/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Inspect evidence" }));
    expect(screen.getByText("Canonical graph")).toBeTruthy();
    expect(screen.getByText("doc-flight")).toBeTruthy();
    expect(screen.getByLabelText("Evidence for Lift changes with airflow.")).toBeTruthy();
  });

  it("keeps legacy receipts playable without claiming an exact excerpt", () => {
    render(<ActiveListeningPlayer playback={{
      ...playback,
      learned_claims: [{
        ...playback.learned_claims[0], evidence_status: "unavailable_legacy", evidence_sources: [],
      }],
    }} title="Legacy lesson" />);
    fireEvent.click(screen.getByRole("button", { name: "Review learned claims" }));
    expect(screen.getByText(/exact excerpt unavailable/)).toBeTruthy();
    expect(screen.getByText(/Evidence records: chunk-1/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Inspect evidence" })).toBeNull();
  });

  it("registers Media Session actions and clears owned state", () => {
    const { unmount } = render(<ActiveListeningPlayer playback={playback} title="Flight lesson" />);
    fireEvent.play(screen.getByLabelText("Audio playback for Flight lesson"));
    expect(mediaSession.setActionHandler).toHaveBeenCalledWith("seekbackward", expect.any(Function));
    expect(mediaSession.setActionHandler).toHaveBeenCalledWith("nexttrack", expect.any(Function));
    expect((mediaSession.metadata as unknown as { title: string }).title).toBe("Flight lesson");
    unmount();
    expect(mediaSession.setActionHandler).toHaveBeenCalledWith("play", null);
    expect(mediaSession.metadata).toBeNull();
    expect(mediaSession.playbackState).toBe("none");
  });

  it("does not clear Media Session state owned by a newer player", () => {
    const first = render(<ActiveListeningPlayer playback={playback} title="First player" />);
    const second = render(<ActiveListeningPlayer playback={{ ...playback, asset_id: "asset-2" }} title="Second player" />);
    const firstAudio = first.getByLabelText("Audio playback for First player") as HTMLAudioElement;
    const pauseFirst = vi.spyOn(firstAudio, "pause");
    fireEvent.play(firstAudio);
    fireEvent.play(second.getByLabelText("Audio playback for Second player"));
    expect(pauseFirst).toHaveBeenCalledOnce();
    expect((mediaSession.metadata as unknown as { title: string }).title).toBe("Second player");
    first.unmount();
    expect((mediaSession.metadata as unknown as { title: string }).title).toBe("Second player");
    expect(handlers.get("play")).toEqual(expect.any(Function));
  });

  it("moves speed radio focus and selection with arrow keys", () => {
    render(<ActiveListeningPlayer playback={playback} title="Flight lesson" />);
    const normal = screen.getByRole("radio", { name: "1x" });
    normal.focus();
    fireEvent.keyDown(normal, { key: "ArrowRight" });
    const faster = screen.getByRole("radio", { name: "1.25x" });
    expect(faster.getAttribute("aria-checked")).toBe("true");
    expect(document.activeElement).toBe(faster);
  });

  it("keeps all controls when Media Session is unsupported", () => {
    Object.defineProperty(navigator, "mediaSession", { configurable: true, value: undefined });
    render(<ActiveListeningPlayer playback={playback} title="Flight lesson" />);
    expect(screen.getByRole("button", { name: "Back 15 seconds" })).toBeTruthy();
    expect(screen.getByRole("radiogroup", { name: "Playback speed" })).toBeTruthy();
  });
});
