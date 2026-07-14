import { StrictMode } from "react";
import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SceneMood } from "./mood";
import { useSceneMomentCue } from "./useSceneMomentCue";

const DAY: SceneMood = { dayPart: "day", weather: "clear" };
const DUSK: SceneMood = { dayPart: "dusk", weather: "clear" };
const NIGHT: SceneMood = { dayPart: "night", weather: "clear" };
const DAWN: SceneMood = { dayPart: "dawn", weather: "clear" };

describe("useSceneMomentCue (SPR-29)", () => {
  it("emits the first committed day → dusk edge once", () => {
    const onCue = vi.fn();
    const { rerender } = renderHook(({ mood }) => useSceneMomentCue(mood, onCue), {
      initialProps: { mood: DAY },
    });
    rerender({ mood: DUSK });
    expect(onCue).toHaveBeenCalledWith({ sequence: 1, moment: "dusk-settle" });
  });

  it("stays silent on initial dusk and weather-only dusk changes", () => {
    const onCue = vi.fn();
    const { rerender } = renderHook(({ mood }) => useSceneMomentCue(mood, onCue), {
      initialProps: { mood: DUSK },
    });
    rerender({ mood: { ...DUSK, weather: "snow" as const } });
    expect(onCue).not.toHaveBeenCalled();
  });

  it("uses one monotonic identity across dusk and daybreak", () => {
    const onCue = vi.fn();
    const { rerender } = renderHook(({ mood }) => useSceneMomentCue(mood, onCue), {
      initialProps: { mood: DAY },
    });
    rerender({ mood: DUSK });
    rerender({ mood: NIGHT });
    rerender({ mood: DAWN });
    expect(onCue.mock.calls).toEqual([
      [{ sequence: 1, moment: "dusk-settle" }],
      [{ sequence: 2, moment: "daybreak" }],
    ]);
  });

  it("does not duplicate dusk under StrictMode", () => {
    const onCue = vi.fn();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <StrictMode>{children}</StrictMode>
    );
    const { rerender } = renderHook(({ mood }) => useSceneMomentCue(mood, onCue), {
      initialProps: { mood: DAY },
      wrapper,
    });
    rerender({ mood: DUSK });
    expect(onCue).toHaveBeenCalledTimes(1);
  });
});
