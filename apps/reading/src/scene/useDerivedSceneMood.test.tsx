import { StrictMode, type PropsWithChildren } from "react";
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  deriveSceneMood,
  nextSceneMoodBoundaryDelayMs,
  useDerivedSceneMood,
  type DerivedSceneMoodEnvironment,
} from "./useDerivedSceneMood";

class FakeMedia extends EventTarget {
  matches = false;
  readonly media = "(prefers-color-scheme: dark)";
  onchange = null;
  addListener = vi.fn();
  removeListener = vi.fn();
  dispatchEvent(event: Event): boolean {
    return super.dispatchEvent(event);
  }
  setDark(dark: boolean) {
    this.matches = dark;
    this.dispatchEvent(new Event("change"));
  }
}

class FakeDocument extends EventTarget {
  hidden = false;
}

function localDate(hour: number, minute = 0): Date {
  return new Date(2026, 6, 14, hour, minute, 0, 0);
}

function harness(hour: number, minute = 0) {
  const media = new FakeMedia();
  const doc = new FakeDocument();
  const callbacks = new Map<number, () => void>();
  let id = 0;
  let now = localDate(hour, minute);
  const environment: DerivedSceneMoodEnvironment = {
    now: () => new Date(now),
    matchMedia: vi.fn(() => media as unknown as MediaQueryList),
    setTimeout: vi.fn((callback) => {
      const next = ++id;
      callbacks.set(next, callback);
      return next;
    }),
    clearTimeout: vi.fn((handle) => callbacks.delete(handle)),
    document: doc as unknown as Document,
  };
  return {
    environment,
    media,
    doc,
    callbacks,
    setNow(next: Date) {
      now = next;
    },
    fireOnlyTimer() {
      expect(callbacks.size).toBe(1);
      const [timerId, callback] = [...callbacks.entries()][0];
      callbacks.delete(timerId);
      act(callback);
    },
  };
}

describe("derived scene mood authority", () => {
  it("derives from fresh local civil time and computes the next bounded edge", () => {
    expect(deriveSceneMood(false, localDate(5, 30)).dayPart).toBe("dawn");
    expect(deriveSceneMood(true, localDate(2)).dayPart).toBe("night");
    expect(nextSceneMoodBoundaryDelayMs(false, localDate(5))).toBe(30 * 60_000);
    expect(nextSceneMoodBoundaryDelayMs(true, localDate(18))).toBe(
      2 * 60 * 60_000,
    );
  });

  it("owns one media subscription and at most one semantic timer", () => {
    const h = harness(6);
    const addSpy = vi.spyOn(h.media, "addEventListener");
    const removeSpy = vi.spyOn(h.media, "removeEventListener");
    const { result, unmount } = renderHook(() =>
      useDerivedSceneMood(h.environment),
    );
    expect(result.current.dayPart).toBe("dawn");
    expect(h.environment.matchMedia).toHaveBeenCalledOnce();
    expect(addSpy).toHaveBeenCalledOnce();
    expect(h.callbacks.size).toBe(1);

    act(() => h.media.setDark(true));
    expect(result.current.dayPart).toBe("night");
    expect(h.callbacks.size).toBe(1);
    unmount();
    expect(removeSpy).toHaveBeenCalledOnce();
    expect(h.callbacks.size).toBe(0);
  });

  it("settles to one subscription and one timer after StrictMode's effect probe", () => {
    const h = harness(6);
    const addMedia = vi.spyOn(h.media, "addEventListener");
    const removeMedia = vi.spyOn(h.media, "removeEventListener");
    const addVisibility = vi.spyOn(h.doc, "addEventListener");
    const removeVisibility = vi.spyOn(h.doc, "removeEventListener");
    const wrapper = ({ children }: PropsWithChildren) => (
      <StrictMode>{children}</StrictMode>
    );
    const { unmount } = renderHook(() => useDerivedSceneMood(h.environment), {
      wrapper,
    });
    expect(addMedia.mock.calls.length - removeMedia.mock.calls.length).toBe(1);
    expect(
      addVisibility.mock.calls.length - removeVisibility.mock.calls.length,
    ).toBe(1);
    expect(h.callbacks.size).toBe(1);
    unmount();
    expect(addMedia.mock.calls.length).toBe(removeMedia.mock.calls.length);
    expect(addVisibility.mock.calls.length).toBe(
      removeVisibility.mock.calls.length,
    );
    expect(h.callbacks.size).toBe(0);
  });

  it("cancels while hidden and recomputes from a fresh Date on return", () => {
    const h = harness(7);
    const { result } = renderHook(() => useDerivedSceneMood(h.environment));
    expect(result.current.dayPart).toBe("dawn");
    h.doc.hidden = true;
    act(() => h.doc.dispatchEvent(new Event("visibilitychange")));
    expect(h.callbacks.size).toBe(0);

    h.setNow(localDate(10));
    h.doc.hidden = false;
    act(() => h.doc.dispatchEvent(new Event("visibilitychange")));
    expect(result.current.dayPart).toBe("day");
    expect(h.callbacks.size).toBe(1);
  });

  it("treats early and late callbacks as hints, never intended mood commands", () => {
    const h = harness(5);
    const { result } = renderHook(() => useDerivedSceneMood(h.environment));
    h.fireOnlyTimer();
    expect(result.current.dayPart).toBe("day");
    expect(h.callbacks.size).toBe(1);

    h.setNow(localDate(6));
    h.fireOnlyTimer();
    expect(result.current.dayPart).toBe("dawn");
    h.setNow(new Date(2026, 6, 15, 2));
    act(() => h.media.setDark(true));
    expect(result.current.dayPart).toBe("night");
    expect(h.callbacks.size).toBe(1);
  });
});
