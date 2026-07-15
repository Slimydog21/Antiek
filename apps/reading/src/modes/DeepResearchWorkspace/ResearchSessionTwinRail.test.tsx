import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ResearchSessionTwinRail } from "./ResearchSessionTwinRail";

describe("ResearchSessionTwinRail", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("returns null for empty parent", () => {
    const { container } = render(<ResearchSessionTwinRail parentAssetId="  " />);
    expect(container.querySelector('[data-testid="research-session-twin-rail"]')).toBeNull();
  });

  it("mounts TwinNotesPanel with autoLoad for a session parent", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            id: "twin-s1",
            parentAssetId: "session-s1",
            isTwin: true,
            status: "ready",
            insights: [{ id: "i1", text: "Session insight" }],
            questions: [],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    render(<ResearchSessionTwinRail parentAssetId="session-s1" />);
    const rail = screen.getByTestId("research-session-twin-rail");
    expect(rail.getAttribute("data-parent-asset-id")).toBe("session-s1");
    await waitFor(() => {
      expect(screen.getByTestId("twin-notes-panel").getAttribute("data-is-live")).toBe(
        "true",
      );
    });
    expect(screen.getByText("Session insight")).toBeTruthy();
  });
});
