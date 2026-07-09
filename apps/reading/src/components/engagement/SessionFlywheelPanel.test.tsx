import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionFlywheelPanel } from "./SessionFlywheelPanel";

const completeSessionFlywheel = vi.fn();

vi.mock("../../api/engagement", () => ({
  completeSessionFlywheel: (...args: unknown[]) =>
    completeSessionFlywheel(...args),
}));

describe("SessionFlywheelPanel residual cl", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    completeSessionFlywheel.mockReset();
  });

  it("completes flywheel with twins and shows context pack", async () => {
    completeSessionFlywheel.mockResolvedValue({
      session_id: "fsess_1",
      spawn_id: "spn_1",
      status: "complete",
      context: {
        asset_id: "book-1",
        twin_units: [],
        source_references: [],
      },
      twin_count: 2,
      ref_count: 0,
      view_format: "html",
      prompt_block: "# Research context pack\n",
    });

    render(
      <SessionFlywheelPanel
        sessionId="fsess_1"
        defaultOutputText="Attention is content-addressable memory."
      />,
    );
    fireEvent.click(screen.getByTestId("session-flywheel-complete"));
    await waitFor(() => {
      expect(completeSessionFlywheel).toHaveBeenCalledWith({
        session_id: "fsess_1",
        output_text: "Attention is content-addressable memory.",
        record_twins: true,
        include_twin_promote: true,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("session-flywheel-result").textContent).toMatch(
        /complete/,
      );
    });
    expect(screen.getByTestId("session-flywheel-prompt-block").textContent).toMatch(
      /Research context/,
    );
    expect(
      screen.getByTestId("session-flywheel-panel").getAttribute("data-view-format"),
    ).toBe("html");
  });

  it("disables complete when output too short", () => {
    render(<SessionFlywheelPanel sessionId="fsess_1" defaultOutputText="ab" />);
    expect(
      (screen.getByTestId("session-flywheel-complete") as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
});
