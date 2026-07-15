/**
 * Scene.test.tsx — SPR-04 milestone 1 + 6 (compositor + freeze).
 *
 *   - The Scene mounts at z-0, pointer-events-none, with all layers in the
 *     documented order (peaks → krea → clouds → snow → penguin).
 *   - reducedMotion → the Scene reports frozen (a single static frame).
 *   - the scenery penguin is marked scenery (distinct from SPR-05's mascot).
 *   - the offline/fallback path renders procedural-only (no live Krea art),
 *     which is the path CI takes (the default Krea mock returns fallback).
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { Scene } from "./Scene";
import type { SceneResult, SceneState } from "../api/krea";

vi.mock("../krea/useKreaStatus", () => ({
  useKreaStatus: () => ({
    status: "ready",
    data: {
      enabled: false,
      key_present: false,
      kill_switch: false,
      gate_verdict: "no_key",
      reasons: ["no_key"],
      budget: { spent_today: 0, cap: 50, remaining: 50 },
      rate_window: { occupancy: 0, max: 6, window_s: 60 },
      cache: { entries: 0, max_entries: 256 },
      last_success_at: null,
      failure_counts: {},
      failures: [],
    },
    error: null,
  }),
}));

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
});

afterEach(() => cleanup());

/** Default offline fetcher — the path CI/sandbox always take (no key). */
const fallbackFetch = async (s: SceneState): Promise<SceneResult> => ({
  enabled: false,
  isFallback: true,
  reason: "no_key",
  scene_key: s.mood,
});

describe("Scene — compositor", () => {
  it("mounts at z-0, pointer-events-none, behind everything", () => {
    const { container } = render(
      <Scene fetchScene={fallbackFetch} reducedMotion />,
    );
    const root = container.querySelector(
      '[data-testid="scene-root"]',
    ) as HTMLElement;
    expect(root).toBeTruthy();
    expect(root.className).toContain("pointer-events-none");
    expect(root.className).toContain("z-0");
    expect(root.className).toContain("absolute");
  });

  it("renders all layers in the documented back→front order", () => {
    const { container } = render(
      <Scene fetchScene={fallbackFetch} reducedMotion />,
    );
    const order = [
      "peaks-layer",
      "krea-art-layer",
      "clouds-layer",
      "snow-layer",
      "penguin-journey",
    ];
    const found = Array.from(container.querySelectorAll("[data-testid]"))
      .map((el) => el.getAttribute("data-testid"))
      .filter((id) => id && order.includes(id));
    // Each named layer is present and they appear in the documented order.
    for (const id of order) expect(found).toContain(id);
    const indices = order.map((id) => found.indexOf(id));
    const sorted = [...indices].sort((a, b) => a - b);
    expect(indices).toEqual(sorted);
  });

  it("under reduced-motion the scene reports frozen (single static frame)", () => {
    const { container } = render(
      <Scene fetchScene={fallbackFetch} reducedMotion />,
    );
    const root = container.querySelector(
      '[data-testid="scene-root"]',
    ) as HTMLElement;
    expect(root.getAttribute("data-scene-frozen")).toBe("true");
  });

  it("the scenery penguin is marked scenery (NOT the interactive mascot)", () => {
    const { container } = render(
      <Scene fetchScene={fallbackFetch} reducedMotion />,
    );
    const peng = container.querySelector(
      '[data-testid="penguin-journey"]',
    ) as HTMLElement;
    expect(peng.getAttribute("data-scenery")).toBe("true");
    // pointer-events-none ⇒ it cannot be interactive.
    expect(peng.className).toContain("pointer-events-none");
  });

  it("the offline/fallback path renders procedural-only (no live Krea art)", async () => {
    const { container, findByTestId } = render(
      <Scene fetchScene={fallbackFetch} reducedMotion />,
    );
    const root = await findByTestId("scene-root");
    // The scene flags fallback; the Krea layer carries no live art.
    expect(root.getAttribute("data-scene-fallback")).toBe("true");
    const krea = container.querySelector(
      '[data-testid="krea-art-layer"]',
    ) as HTMLElement;
    expect(krea.getAttribute("data-krea")).toBe("fallback");
  });

  it("preserves the Krea status badge mount and status wiring (PR 144)", () => {
    const { getByTestId } = render(
      <Scene fetchScene={fallbackFetch} reducedMotion />,
    );
    const badge = getByTestId("scene-status-badge");
    expect(badge.getAttribute("data-reason")).toBe("no_key");
    expect(badge.textContent).toContain("scene: procedural / no key");
  });

  it("keeps derived theme/time authority dormant under an explicit mood", () => {
    const matchMedia = vi.spyOn(window, "matchMedia");
    render(
      <Scene
        mood={{ dayPart: "dusk", weather: "snow" }}
        fetchScene={fallbackFetch}
        reducedMotion
      />,
    );
    expect(
      matchMedia.mock.calls.some(([query]) =>
        String(query).includes("prefers-color-scheme"),
      ),
    ).toBe(false);
    matchMedia.mockRestore();
  });
});
