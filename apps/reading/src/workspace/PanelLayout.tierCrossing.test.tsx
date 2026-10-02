import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

/**
 * PanelLayout returned early for the phone tier before three of its hooks
 * ran, so a window resized across 768 px changed the hook count between
 * renders and React threw. Every hook now runs before that return.
 */

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "sm" as string } }));

vi.mock("./useViewportTier", () => ({
  useViewportTier: () => tierRef.current,
}));

import { PanelLayout } from "./PanelLayout";

describe("PanelLayout across the phone tier boundary", () => {
  afterEach(() => {
    cleanup();
    tierRef.current = "sm";
  });

  it.each([
    ["sm", "md"],
    ["md", "sm"],
    ["sm", "xl"],
  ])("re-renders from %s to %s without a hook-order error", (from, to) => {
    tierRef.current = from;
    const { rerender } = render(<PanelLayout mainSlot={<p>Main content</p>} />);
    expect(screen.getByText("Main content")).toBeTruthy();
    tierRef.current = to;
    expect(() => rerender(<PanelLayout mainSlot={<p>Main content</p>} />)).not.toThrow();
    expect(screen.getByText("Main content")).toBeTruthy();
  });
});
