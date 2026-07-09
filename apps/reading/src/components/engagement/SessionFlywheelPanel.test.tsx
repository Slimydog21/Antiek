import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionFlywheelPanel } from "./SessionFlywheelPanel";

const completeSessionFlywheel = vi.fn();

vi.mock("../../api/engagement", () => ({
  completeSessionFlywheel: (...args: unknown[]) =>
    completeSessionFlywheel(...args),
}));

describe("SessionFlywheelPanel residual cl/ee", () => {
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
        twin_units: [{ unit_id: "t1" }, { unit_id: "t2" }],
        source_references: [],
        twin_count: 2,
        ref_count: 0,
        research_tier: "wrestle",
      },
      view_format: "html",
      prompt_block: "# Research context pack\n",
      research_tier: "wrestle",
      usage_event: {
        task_class: "wrestle",
        outcome: "worked",
        source: "session_flywheel",
      },
    });

    const onCompleted = vi.fn();
    render(
      <SessionFlywheelPanel
        sessionId="fsess_1"
        defaultOutputText="Attention is content-addressable memory."
        onCompleted={onCompleted}
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
    // Residual (ee): parent notified so research context can remount.
    await waitFor(() => {
      expect(onCompleted).toHaveBeenCalled();
    });
    expect(onCompleted.mock.calls[0][0].view_format).toBe("html");
    expect(onCompleted.mock.calls[0][0].status).toBe("complete");
    // Residual (hj): machine-readable session flywheel metrics.
    const metrics = screen.getByTestId("session-flywheel-metrics");
    expect(metrics.getAttribute("data-status")).toBe("complete");
    expect(metrics.getAttribute("data-session-id")).toBe("fsess_1");
    expect(metrics.getAttribute("data-spawn-id")).toBe("spn_1");
    expect(metrics.getAttribute("data-twin-count")).toBe("2");
    expect(metrics.getAttribute("data-ref-count")).toBe("0");
    expect(metrics.getAttribute("data-record-twins")).toBe("true");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.textContent).toMatch(/Session flywheel/);
    // Residual (jt): research_tier + Antiek-bench task_class audit.
    expect(metrics.getAttribute("data-research-tier")).toBe("wrestle");
    expect(metrics.getAttribute("data-usage-task-class")).toBe("wrestle");
    expect(metrics.getAttribute("data-usage-outcome")).toBe("worked");
    expect(screen.getByTestId("session-flywheel-research-tier").textContent).toBe(
      "wrestle",
    );
    expect(
      screen.getByTestId("session-flywheel-usage-task-class").textContent,
    ).toMatch(/wrestle/);
    // Residual (kq): pack context.research_tier chrome.
    expect(metrics.getAttribute("data-context-research-tier")).toBe("wrestle");
    expect(
      screen
        .getByTestId("session-flywheel-result")
        .getAttribute("data-context-research-tier"),
    ).toBe("wrestle");
    expect(
      screen.getByTestId("session-flywheel-context-research-tier").textContent,
    ).toMatch(/wrestle/);
  });

  it("falls back to context.research_tier when session tier absent (kq)", async () => {
    completeSessionFlywheel.mockResolvedValue({
      session_id: "fsess_2",
      spawn_id: "spn_2",
      status: "complete",
      context: {
        asset_id: "book-2",
        twin_units: [],
        source_references: [],
        twin_count: 0,
        ref_count: 0,
        research_tier: "deep",
      },
      view_format: "html",
      prompt_block: "# pack\n",
      research_tier: null,
      usage_event: null,
    });
    render(
      <SessionFlywheelPanel
        sessionId="fsess_2"
        defaultOutputText="Fallback pack tier path."
      />,
    );
    fireEvent.click(screen.getByTestId("session-flywheel-complete"));
    await waitFor(() => {
      expect(screen.getByTestId("session-flywheel-research-tier").textContent).toBe(
        "deep",
      );
    });
    expect(
      screen.getByTestId("session-flywheel-metrics").getAttribute("data-research-tier"),
    ).toBe("deep");
    expect(
      screen
        .getByTestId("session-flywheel-metrics")
        .getAttribute("data-context-research-tier"),
    ).toBe("deep");
  });

  it("disables complete when output too short", () => {
    render(<SessionFlywheelPanel sessionId="fsess_1" defaultOutputText="ab" />);
    expect(
      (screen.getByTestId("session-flywheel-complete") as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("links to Settings for driver & budget (ii)", () => {
    render(<SessionFlywheelPanel sessionId="fsess_1" />);
    const link = screen.getByTestId("session-flywheel-settings-link");
    expect(link.getAttribute("href")).toBe("/settings");
    expect(link.textContent).toMatch(/driver & budget/i);
  });
});
