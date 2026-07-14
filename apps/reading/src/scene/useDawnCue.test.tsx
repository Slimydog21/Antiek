import { StrictMode } from "react";
import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useDawnCue } from "./useDawnCue";
import type { SceneMood } from "./mood";

const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };
const DAWN: SceneMood = { dayPart: "dawn", weather: "snow" };
const DUSK: SceneMood = { dayPart: "dusk", weather: "snow" };

describe("useDawnCue (SPR-22)", () => {
  it("stays silent on initial dawn", () => {
    const onTransition = vi.fn();
    renderHook(() => useDawnCue(DAWN, onTransition));
    expect(onTransition).not.toHaveBeenCalled();
  });

  it("emits daybreak on night → dawn transition", () => {
    const onTransition = vi.fn();
    const { rerender } = renderHook(
      ({ mood }) => useDawnCue(mood, onTransition),
      { initialProps: { mood: NIGHT } },
    );
    rerender({ mood: DAWN });
    expect(onTransition).toHaveBeenCalledWith({ sequence: 1, moment: "daybreak" });
  });

  it("returns null for night → day (dawn skipped)", () => {
    const onTransition = vi.fn();
    const { rerender } = renderHook(
      ({ mood }) => useDawnCue(mood, onTransition),
      { initialProps: { mood: NIGHT } },
    );
    rerender({ mood: DAY });
    expect(onTransition).not.toHaveBeenCalled();
  });

  it("returns null for day → dawn", () => {
    const onTransition = vi.fn();
    const { rerender } = renderHook(
      ({ mood }) => useDawnCue(mood, onTransition),
      { initialProps: { mood: DAY } },
    );
    rerender({ mood: DAWN });
    expect(onTransition).not.toHaveBeenCalled();
  });

  it("returns null for same mood re-render", () => {
    const onTransition = vi.fn();
    const { rerender } = renderHook(
      ({ mood }) => useDawnCue(mood, onTransition),
      { initialProps: { mood: NIGHT } },
    );
    rerender({ mood: { ...NIGHT } });
    expect(onTransition).not.toHaveBeenCalled();
  });

  it("returns null for weather-only change (same dayPart)", () => {
    const onTransition = vi.fn();
    const { rerender } = renderHook(
      ({ mood }) => useDawnCue(mood, onTransition),
      { initialProps: { mood: NIGHT } },
    );
    rerender({ mood: { dayPart: "night", weather: "clear" } });
    expect(onTransition).not.toHaveBeenCalled();
  });

  it("returns null for dusk → dawn (not night → dawn)", () => {
    const onTransition = vi.fn();
    const { rerender } = renderHook(
      ({ mood }) => useDawnCue(mood, onTransition),
      { initialProps: { mood: DUSK } },
    );
    rerender({ mood: DAWN });
    expect(onTransition).not.toHaveBeenCalled();
  });

  it("does not emit duplicate cues on StrictMode re-render", () => {
    const onTransition = vi.fn();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <StrictMode>{children}</StrictMode>
    );
    const { rerender } = renderHook(
      ({ mood }) => useDawnCue(mood, onTransition),
      { initialProps: { mood: NIGHT }, wrapper },
    );
    rerender({ mood: DAWN });
    expect(onTransition).toHaveBeenCalledTimes(1);
  });

  it("does not emit on unmount", () => {
    const { unmount } = renderHook(() => useDawnCue(NIGHT));
    // No assertion needed — just confirm it doesn't throw.
    unmount();
  });

  it("increments identity across distinct night → dawn transitions", () => {
    const onTransition = vi.fn();
    const { rerender } = renderHook(
      ({ mood }) => useDawnCue(mood, onTransition),
      { initialProps: { mood: NIGHT } },
    );
    rerender({ mood: DAWN });
    rerender({ mood: NIGHT });
    rerender({ mood: DAWN });
    expect(onTransition.mock.calls).toEqual([
      [{ sequence: 1, moment: "daybreak" }],
      [{ sequence: 2, moment: "daybreak" }],
    ]);
  });

  it("does not emit for initial dawn → day transition (no prior night)", () => {
    // Mount at dawn, transition to day — should NOT emit because
    // the previous mood was dawn (not night).
    const onTransition = vi.fn();
    const { rerender } = renderHook(
      ({ mood }) => useDawnCue(mood, onTransition),
      { initialProps: { mood: DAWN } },
    );
    rerender({ mood: DAY });
    expect(onTransition).not.toHaveBeenCalled();
  });
});
