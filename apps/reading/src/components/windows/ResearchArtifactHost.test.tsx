import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

let sessionGeneration = 1;

vi.mock("../../lib/auth", () => ({
  useAuth: () => ({ sessionGeneration }),
}));

vi.mock("../../lib/api", () => ({ API_BASE: "https://api.antiek.test" }));

import ResearchArtifactHost from "./ResearchArtifactHost";

afterEach(() => {
  cleanup();
  sessionGeneration = 1;
});

describe("ResearchArtifactHost private-session boundary", () => {
  it("replaces the iframe when the authenticated session generation changes", () => {
    const view = render(<ResearchArtifactHost investigationId="same/display" />);
    const aliceFrame = screen.getByTitle("Private research artifact");
    expect(aliceFrame.getAttribute("src")).toBe(
      "https://api.antiek.test/research/same%2Fdisplay/artifact/view",
    );
    expect(aliceFrame.getAttribute("sandbox")).toBe("allow-scripts");
    expect(aliceFrame.getAttribute("referrerpolicy")).toBe("no-referrer");

    sessionGeneration = 2;
    view.rerender(<ResearchArtifactHost investigationId="same/display" />);
    const bobFrame = screen.getByTitle("Private research artifact");
    expect(bobFrame).not.toBe(aliceFrame);
    expect(aliceFrame.isConnected).toBe(false);
  });

  it("renders no private frame without an investigation identity", () => {
    render(<ResearchArtifactHost />);
    expect(screen.queryByTitle("Private research artifact")).toBeNull();
    expect(screen.getByText("Research artifact identity is unavailable.").isConnected).toBe(true);
  });
});
