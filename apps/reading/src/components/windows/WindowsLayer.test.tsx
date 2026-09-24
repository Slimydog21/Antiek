import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import WindowsLayer from "./WindowsLayer";
import { useWindows } from "../../workspace/windowsStore";

afterEach(() => {
  cleanup();
  useWindows.getState().reset();
});

describe("WindowsLayer coordinate contract", () => {
  it("keeps one inert coordinate origin mounted before the first window opens", () => {
    const { container } = render(<WindowsLayer />);
    const layer = container.querySelector("[data-windows-layer]");
    expect(layer).toBeTruthy();
    expect(layer?.className).toContain("pointer-events-none");
    expect(layer?.children).toHaveLength(0);
  });
});
