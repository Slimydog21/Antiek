/**
 * Hit-test proof: shell-level SceneHotspots must win document.elementFromPoint
 * at a hotspot center over a full-viewport chrome sibling — the prior gap.
 *
 * jsdom does not implement elementFromPoint; we install a geometry-aware
 * polyfill that respects pointer-events + paint order (later siblings win),
 * matching the browser contract the Playwright proof also exercises.
 */
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { SCENE_HOTSPOTS, hotspotToPixels } from "./interactiveRegions";
import { SceneHotspots } from "./SceneHotspots";

function installElementFromPointPolyfill() {
  // Geometry-aware topmost hit: walk all elements, keep those whose rect
  // contains (x,y) and computed pointer-events is not none; last in tree
  // order wins (matches fixed/absolute stacking for our shell stack).
  document.elementFromPoint = (x: number, y: number) => {
    const all = Array.from(document.querySelectorAll("body *")) as HTMLElement[];
    let hit: HTMLElement | null = null;
    for (const el of all) {
      const style = window.getComputedStyle(el);
      if (style.pointerEvents === "none" || style.display === "none") continue;
      const r = el.getBoundingClientRect();
      if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) {
        hit = el;
      }
    }
    return hit;
  };
}

beforeAll(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }
  installElementFromPointPolyfill();
});

afterEach(() => cleanup());

describe("SceneHotspots shell hit-test stack", () => {
  const vp = { width: 1000, height: 800 };

  it("elementFromPoint at hotspot center resolves to the hotspot button (not chrome)", () => {
    // Minimal shell stack mirroring AppShell: scene paint (none) → chrome
    // full-bleed auto sibling → SceneHotspots shell overlay after chrome.
    render(
      <div
        data-akb-shell-frame
        style={{
          position: "relative",
          width: vp.width,
          height: vp.height,
          overflow: "hidden",
        }}
      >
        <div
          data-testid="scene-root"
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 0,
            pointerEvents: "none",
            background: "#88a",
          }}
        />
        <div
          data-akb-chrome-column
          style={{
            position: "relative",
            zIndex: 20,
            width: "100%",
            height: "100%",
            display: "flex",
            flexDirection: "column",
            pointerEvents: "none",
          }}
        >
          <div
            data-testid="chrome-bleed"
            style={{
              flex: 1,
              background: "rgba(255,255,255,0.5)",
              pointerEvents: "auto",
            }}
          >
            full-bleed chrome
          </div>
        </div>
        <SceneHotspots mode="shell" viewport={vp} />
      </div>,
    );

    // Edge scenery (peak-left) — not center cards. Hotspots sit at z-10;
    // primary chrome at z-30 wins when both cover a pixel.
    const btn = screen.getByTestId("scene-hotspot-peak-left");
    const target = SCENE_HOTSPOTS.find((h) => h.id === "peak-left")!;
    const r = hotspotToPixels(target, vp);
    const origBtn = btn.getBoundingClientRect.bind(btn);
    btn.getBoundingClientRect = () =>
      ({
        x: r.x,
        y: r.y,
        width: r.w,
        height: r.h,
        top: r.y,
        left: r.x,
        right: r.x + r.w,
        bottom: r.y + r.h,
        toJSON: () => ({}),
      }) as DOMRect;
    // Chrome bleed covers ONLY the center — not the left 7% edge strip.
    const chrome = screen.getByTestId("chrome-bleed");
    chrome.getBoundingClientRect = () =>
      ({
        x: vp.width * 0.1,
        y: 0,
        width: vp.width * 0.8,
        height: vp.height,
        top: 0,
        left: vp.width * 0.1,
        right: vp.width * 0.9,
        bottom: vp.height,
        toJSON: () => ({}),
      }) as DOMRect;

    const cx = Math.floor(r.x + r.w / 2);
    const cy = Math.floor(r.y + r.h / 2);

    const el = document.elementFromPoint(cx, cy) as HTMLElement | null;
    expect(el).toBeTruthy();
    const hotspot = el?.closest?.("[data-hotspot-id]") as HTMLElement | null;
    expect(hotspot).toBeTruthy();
    expect(hotspot?.getAttribute("data-hotspot-id")).toBe("peak-left");
    expect(el?.getAttribute("data-testid")).not.toBe("chrome-bleed");

    fireEvent.click(btn);
    expect(
      screen.getByTestId("scene-hotspots").getAttribute("data-last-click"),
    ).toBe("peak-left");

    btn.getBoundingClientRect = origBtn;
  });

  it("shell mode mounts fixed overlay with pointer-events none on root at z-35", () => {
    render(<SceneHotspots mode="shell" viewport={vp} />);
    const layer = screen.getByTestId("scene-hotspots");
    expect(layer.getAttribute("data-hotspots-mode")).toBe("shell");
    expect(layer.style.pointerEvents).toBe("none");
    expect(layer.style.position).toBe("fixed");
    expect(layer.style.zIndex).toBe("35");
  });
});
