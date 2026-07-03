import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { SceneStatusBadge, sceneStatusReason } from "./SceneStatusBadge";
import type { KreaStatusSnapshot } from "../api/krea";

afterEach(() => cleanup());

function status(over: Partial<KreaStatusSnapshot> = {}): KreaStatusSnapshot {
  return {
    enabled: true,
    key_present: true,
    kill_switch: false,
    gate_verdict: null,
    reasons: [],
    budget: { spent_today: 0, cap: 50, remaining: 50 },
    rate_window: { occupancy: 0, max: 6, window_s: 60 },
    cache: { entries: 0, max_entries: 256 },
    last_success_at: null,
    failure_counts: {},
    failures: [],
    ...over,
  };
}

describe("SceneStatusBadge", () => {
  it("renders nothing when Krea is healthy", () => {
    const { queryByTestId } = render(<SceneStatusBadge status={status()} />);
    expect(queryByTestId("scene-status-badge")).toBeNull();
  });

  it("shows the active gate verdict", () => {
    const { getByTestId } = render(
      <SceneStatusBadge status={status({ enabled: false, gate_verdict: "no_key", key_present: false })} />,
    );
    const badge = getByTestId("scene-status-badge");
    expect(badge.textContent).toBe("scene: procedural / no key. No live Krea.");
    expect(badge.getAttribute("data-reason")).toBe("no_key");
  });

  it("falls back to the latest failure-ring reason for upstream failures", () => {
    const snapshot = status({
      failures: [
        { timestamp: "2026-07-02T00:00:00Z", reason: "upstream_error", upstream_status: 500 },
      ],
      failure_counts: { upstream_error: 1 },
    });
    expect(sceneStatusReason(snapshot)).toBe("upstream_error");
    const { getByTestId } = render(<SceneStatusBadge status={snapshot} />);
    expect(getByTestId("scene-status-badge").textContent).toContain("upstream error");
  });

  it("shows status-offline when /krea/status itself cannot be reached", () => {
    const { getByTestId } = render(<SceneStatusBadge status={null} error="offline" />);
    expect(getByTestId("scene-status-badge").textContent).toContain("status offline");
  });
});
