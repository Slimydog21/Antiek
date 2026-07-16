import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TwinNotesPanel } from "./TwinNotesPanel";
import { emptyTwin } from "./twinDocument";

describe("TwinNotesPanel", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders demo twin for an asset when no live twin", () => {
    render(<TwinNotesPanel parentAssetId="doc-42" />);
    expect(screen.getByTestId("twin-notes-panel").getAttribute("data-is-demo")).toBe(
      "true",
    );
    expect(screen.getByTestId("twin-notes-insights").children.length).toBeGreaterThan(
      0,
    );
    expect(screen.getByTestId("twin-notes-questions").children.length).toBeGreaterThan(
      0,
    );
    // Living-TV densify — recursive note-taker companion consumes session brand.
    expect(screen.getByTestId("twin-notes-werner-brand")).toBeTruthy();
    const livingTv = screen.getByTestId(
      "twin-notes-living-tv-art",
    ) as HTMLImageElement;
    expect(livingTv.getAttribute("src") ?? "").toMatch(
      /werner_living_tv_session_v1/,
    );
  });

  it("shows empty state when demo disabled and no twin", () => {
    render(<TwinNotesPanel parentAssetId="doc" allowDemo={false} />);
    expect(screen.getByTestId("twin-notes-panel-empty")).toBeTruthy();
  });

  it("renders live empty twin status", () => {
    render(
      <TwinNotesPanel
        parentAssetId="doc"
        twin={emptyTwin("doc", "t1")}
        allowDemo={false}
      />,
    );
    expect(screen.getByTestId("twin-notes-panel").getAttribute("data-twin-status")).toBe(
      "empty",
    );
    expect(screen.getByTestId("twin-notes-panel").getAttribute("data-is-demo")).toBe(
      "false",
    );
  });

  it("autoLoad promotes a live twin and marks data-is-live", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            id: "twin-live",
            parentAssetId: "doc-live",
            isTwin: true,
            status: "ready",
            insights: [{ id: "i1", text: "Fetched insight" }],
            questions: [{ id: "q1", text: "Fetched Q?", open: true }],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    render(<TwinNotesPanel parentAssetId="doc-live" autoLoad allowDemo={false} />);
    await waitFor(() => {
      expect(screen.getByTestId("twin-notes-panel").getAttribute("data-is-live")).toBe(
        "true",
      );
    });
    expect(screen.getByText("Fetched insight")).toBeTruthy();
    expect(screen.getByTestId("twin-notes-panel").getAttribute("data-is-demo")).toBe(
      "false",
    );
  });
});
