import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { SCENE_HOTSPOTS, hotspotToPixels } from "./interactiveRegions";
import { SceneHotspots } from "./SceneHotspots";
import { WERNER_EXPERIENCE_EVENT } from "../werner/reactionBus";

afterEach(() => cleanup());

describe("SceneHotspots — interactive Flipbook-feel regions", () => {
  const vp = { width: 1000, height: 800 };

  it("renders one button per hotspot with pointer-events auto", () => {
    render(<SceneHotspots viewport={vp} mode="inline" />);
    const layer = screen.getByTestId("scene-hotspots");
    expect(layer.getAttribute("data-hotspots-mode")).toBe("inline");
    expect(layer.getAttribute("data-hotspot-count")).toBe(
      String(SCENE_HOTSPOTS.length),
    );
    for (const h of SCENE_HOTSPOTS) {
      const btn = screen.getByTestId(`scene-hotspot-${h.id}`);
      expect(btn.style.pointerEvents).toBe("auto");
      const r = hotspotToPixels(h, vp);
      expect(parseFloat(btn.style.left)).toBeCloseTo(r.x, 0);
      expect(parseFloat(btn.style.width)).toBeCloseTo(r.w, 0);
    }
  });

  it("hover path sets data-hovered via shipped activate path", () => {
    const onActivate = vi.fn();
    render(<SceneHotspots viewport={vp} mode="inline" onActivate={onActivate} />);
    const target = SCENE_HOTSPOTS.find((h) => h.id === "peak-left")!;
    fireEvent.mouseEnter(screen.getByTestId(`scene-hotspot-${target.id}`));
    expect(onActivate).toHaveBeenCalledWith("peak-left", "hover");
    expect(screen.getByTestId("scene-hotspots").getAttribute("data-hovered")).toBe(
      "peak-left",
    );
  });

  it("hover emits one Werner highlight per hotspot per mount (no spam)", () => {
    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (d?.experience) seen.push(d.experience);
    };
    window.addEventListener(WERNER_EXPERIENCE_EVENT, onExp);
    render(<SceneHotspots viewport={vp} mode="inline" />);
    const btn = screen.getByTestId("scene-hotspot-peak-left");
    fireEvent.mouseEnter(btn);
    fireEvent.mouseLeave(btn);
    fireEvent.mouseEnter(btn);
    fireEvent.mouseEnter(screen.getByTestId("scene-hotspot-peak-right"));
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, onExp);
    // peak-left once + peak-right once — second peak-left hover must not re-fire.
    expect(seen.filter((e) => e === "highlight")).toHaveLength(2);
  });

  it("click path records last-click and uses hotspot geometry", () => {
    const onActivate = vi.fn();
    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (d?.experience) seen.push(d.experience);
    };
    window.addEventListener(WERNER_EXPERIENCE_EVENT, onExp);
    render(<SceneHotspots viewport={vp} mode="inline" onActivate={onActivate} />);
    fireEvent.click(screen.getByTestId("scene-hotspot-peak-right"));
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, onExp);
    expect(onActivate).toHaveBeenCalledWith("peak-right", "click");
    expect(
      screen.getByTestId("scene-hotspots").getAttribute("data-last-click"),
    ).toBe("peak-right");
    expect(seen).toContain("highlight");
  });
});
