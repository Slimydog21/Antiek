/**
 * FFX SPR-04 M8 (A-12): the procedural-scene badge is an operator
 * diagnostic. A production render shows it only with ?scene=debug; dev
 * builds (and Storybook) keep showing it.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { SceneStatusBadge } from "./SceneStatusBadge";
import type { KreaStatusSnapshot } from "../api/krea";

const NO_KEY: KreaStatusSnapshot = {
  enabled: false,
  key_present: false,
  kill_switch: false,
  gate_verdict: "no_key",
  reasons: [],
  budget: { spent_today: 0, cap: 50, remaining: 50 },
  rate_window: { occupancy: 0, max: 6, window_s: 60 },
  cache: { entries: 0, max_entries: 256 },
  last_success_at: null,
  failure_counts: {},
  failures: [],
};

function production() {
  vi.stubEnv("DEV", false);
  vi.stubEnv("PROD", true);
  vi.stubEnv("STORYBOOK", "");
}

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  window.history.replaceState(null, "", "/");
});

describe("SceneStatusBadge gate (A-12)", () => {
  it("is absent in a production render without the debug flag", () => {
    production();
    window.history.replaceState(null, "", "/research");
    const { queryByTestId, container } = render(<SceneStatusBadge status={NO_KEY} />);
    expect(queryByTestId("scene-status-badge")).toBeNull();
    expect(container.textContent).not.toContain("no key");
  });

  it("is absent in production when Krea status is unreachable, too", () => {
    production();
    const { queryByTestId } = render(<SceneStatusBadge status={null} error="offline" />);
    expect(queryByTestId("scene-status-badge")).toBeNull();
  });

  it("shows in production with ?scene=debug", () => {
    production();
    window.history.replaceState(null, "", "/research?scene=debug");
    const { getByTestId } = render(<SceneStatusBadge status={NO_KEY} />);
    expect(getByTestId("scene-status-badge").textContent).toBe("scene: procedural / no key. No live Krea.");
  });

  it("still shows in a dev build", () => {
    vi.stubEnv("DEV", true);
    const { getByTestId } = render(<SceneStatusBadge status={NO_KEY} />);
    expect(getByTestId("scene-status-badge")).toBeTruthy();
  });
});
