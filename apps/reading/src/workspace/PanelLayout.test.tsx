import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PanelLayout } from "./PanelLayout";
import { useWorkspace } from "./WorkspaceStore";

vi.mock("./PanelLayoutPanel", () => ({ PanelLayoutPanel: () => null }));

const originalWidth = Object.getOwnPropertyDescriptor(window, "innerWidth");

function resizeTo(width: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width, writable: true });
  act(() => {
    window.dispatchEvent(new Event("resize"));
    vi.advanceTimersByTime(81);
  });
}

describe("PanelLayout viewport crossing", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useWorkspace.getState().reset();
  });

  afterEach(() => {
    vi.useRealTimers();
    if (originalWidth) Object.defineProperty(window, "innerWidth", originalWidth);
    else Reflect.deleteProperty(window, "innerWidth");
  });

  it("keeps the route mounted when the viewport crosses the small-screen boundary in both directions", () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 767, writable: true });
    render(<PanelLayout mainSlot={<p>Route remains mounted</p>} />);

    screen.getByText("Route remains mounted");
    screen.getByText(/Antiek is designed for/);
    expect(screen.queryByLabelText("Left dock")).toBeNull();

    resizeTo(768);
    screen.getByText("Route remains mounted");
    screen.getByLabelText("Left dock");
    expect(screen.queryByText(/Antiek is designed for/)).toBeNull();

    resizeTo(767);
    screen.getByText("Route remains mounted");
    screen.getByText(/Antiek is designed for/);
    expect(screen.queryByLabelText("Left dock")).toBeNull();
  });
});
