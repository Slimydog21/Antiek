// SPR-07 M4 — scrollToChunk + scrollToChunkWhenReady tests.
//
// The function looks up a chunk by ``data-chunk-id`` attribute,
// scrolls it into view, and applies a 2-second pulse class. We
// verify:
//   - present chunk → scrollIntoView called, pulse class added,
//     class removed after the timeout.
//   - missing chunk → returns false, no DOM mutation.
//   - "WhenReady" polls and resolves when the chunk appears.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  _PULSE_DURATION_MS_FOR_TEST,
  scrollToChunk,
  scrollToChunkWhenReady,
} from "../scrollToChunk";

describe("scrollToChunk", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });
  afterEach(() => {
    document.body.innerHTML = "";
    vi.useRealTimers();
  });

  it("returns false when the chunk is not in the DOM", () => {
    expect(scrollToChunk("missing")).toBe(false);
  });

  it("scrolls + pulses the chunk when present", () => {
    vi.useFakeTimers();
    const el = document.createElement("span");
    el.dataset.chunkId = "c-1";
    el.textContent = "passage";
    el.scrollIntoView = vi.fn();
    document.body.appendChild(el);

    expect(scrollToChunk("c-1")).toBe(true);
    expect(el.scrollIntoView).toHaveBeenCalledWith({
      behavior: "smooth",
      block: "center",
    });
    expect(el.classList.contains("ring-amber-400")).toBe(true);
    expect(el.classList.contains("ring-2")).toBe(true);
    expect(el.classList.contains("bg-amber-50")).toBe(true);

    // After the pulse duration, classes are removed.
    vi.advanceTimersByTime(_PULSE_DURATION_MS_FOR_TEST + 10);
    expect(el.classList.contains("ring-amber-400")).toBe(false);
    expect(el.classList.contains("ring-2")).toBe(false);
  });

  it("handles chunk ids that need CSS escaping", () => {
    const el = document.createElement("span");
    // Chunk id with a colon — CSS attribute selectors need escaping.
    el.setAttribute("data-chunk-id", "chunk:abc-123");
    el.scrollIntoView = vi.fn();
    document.body.appendChild(el);
    expect(scrollToChunk("chunk:abc-123")).toBe(true);
  });
});

describe("scrollToChunkWhenReady", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("resolves true when chunk appears within the timeout", async () => {
    const promise = scrollToChunkWhenReady("c-late", 1000);
    // Insert after a short delay.
    setTimeout(() => {
      const el = document.createElement("span");
      el.dataset.chunkId = "c-late";
      el.scrollIntoView = vi.fn();
      document.body.appendChild(el);
    }, 150);
    const found = await promise;
    expect(found).toBe(true);
  });

  it("resolves false when chunk never appears (timeout)", async () => {
    const found = await scrollToChunkWhenReady("c-never", 200);
    expect(found).toBe(false);
  });
});
