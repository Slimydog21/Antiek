import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Event } from "../generated/types";
import TrajectoryReplay from "./TrajectoryReplay";

function replayEvent(
  id: string,
  emittedAt: string,
  actionType: Event["action_type"],
): Event {
  return {
    event_id: id,
    investigation_id: "inv-replay",
    role: "synthesizer",
    action_type: actionType,
    payload: {
      action_type: actionType,
      marker: id,
    } as never,
    param_version: "0.1.0",
    schema_version: 6,
    emitted_at: emittedAt,
  };
}

const UNSORTED_EVENTS: Event[] = [
  replayEvent("event-late", "2026-07-01T12:00:03Z", "synthesize.delivered"),
  replayEvent("event-early", "2026-07-01T12:00:01Z", "phase.enter"),
  replayEvent("event-middle", "2026-07-01T12:00:02Z", "dispatch.call"),
];

beforeEach(() => {
  vi.useRealTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("TrajectoryReplay", () => {
  it("renders an honest empty state when no trajectory events exist", () => {
    render(<TrajectoryReplay events={[]} />);

    expect(screen.getByText("No events in this trajectory yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Play" })).toBeNull();
  });

  it("sorts events by emitted_at before rendering the first frame", () => {
    render(<TrajectoryReplay events={UNSORTED_EVENTS} />);

    expect(screen.getByText("1 / 3")).toBeTruthy();
    expect(screen.getByText(/event_id: event-early/)).toBeTruthy();
    expect(screen.getAllByText(/phase.enter/).length).toBeGreaterThanOrEqual(1);
  });

  it("dedupes replayed event ids before sorting and counting frames", () => {
    render(
      <TrajectoryReplay
        events={[
          replayEvent("event-repeat", "2026-07-01T12:00:03Z", "synthesize.delivered"),
          replayEvent("event-repeat", "2026-07-01T12:00:01Z", "phase.enter"),
          replayEvent("event-second", "2026-07-01T12:00:02Z", "dispatch.call"),
        ]}
      />,
    );

    expect(screen.getByText("1 / 2")).toBeTruthy();
    expect(screen.getByText(/event_id: event-second/)).toBeTruthy();
    expect(screen.queryByText(/phase.enter/)).toBeNull();
  });

  it("scrubs with the range input and pauses on manual navigation", async () => {
    const user = userEvent.setup();
    render(<TrajectoryReplay events={UNSORTED_EVENTS} />);

    const play = screen.getByRole("button", { name: "Play" });
    await user.click(play);
    expect(screen.getByRole("button", { name: "Pause" })).toBeTruthy();

    fireEvent.change(screen.getByRole("slider"), { target: { value: "2" } });

    expect(screen.getByRole("button", { name: "Play" })).toBeTruthy();
    expect(screen.getByText("3 / 3")).toBeTruthy();
    expect(screen.getByText(/event_id: event-late/)).toBeTruthy();
  });

  it("jumps to a ReplayStepList event and pauses playback", async () => {
    const user = userEvent.setup();
    render(<TrajectoryReplay events={UNSORTED_EVENTS} />);

    await user.click(screen.getByRole("button", { name: "Play" }));
    expect(screen.getByRole("button", { name: "Pause" })).toBeTruthy();

    act(() => {
      window.dispatchEvent(
        new CustomEvent("antiek:replay:goto", {
          detail: { eventId: "event-middle" },
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Play" })).toBeTruthy();
      expect(screen.getByText("2 / 3")).toBeTruthy();
      expect(screen.getByText(/event_id: event-middle/)).toBeTruthy();
    });
  });

  it("ignores malformed ReplayStepList jumps without moving the frame", () => {
    render(<TrajectoryReplay events={UNSORTED_EVENTS} />);

    window.dispatchEvent(
      new CustomEvent("antiek:replay:goto", {
        detail: { eventId: "event-does-not-exist" },
      }),
    );
    window.dispatchEvent(new CustomEvent("antiek:replay:goto", { detail: {} }));

    expect(screen.getByText("1 / 3")).toBeTruthy();
    expect(screen.getByText(/event_id: event-early/)).toBeTruthy();
  });

  it("pauses when the operator clicks Pause", async () => {
    const user = userEvent.setup();
    render(<TrajectoryReplay events={UNSORTED_EVENTS} />);

    await user.click(screen.getByRole("button", { name: "Play" }));
    expect(screen.getByRole("button", { name: "Pause" })).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Pause" }));

    expect(screen.getByRole("button", { name: "Play" })).toBeTruthy();
    expect(screen.getByText("1 / 3")).toBeTruthy();
  });

  it("plays forward at the configured speed and stops at the final event", async () => {
    vi.useFakeTimers();
    render(<TrajectoryReplay events={UNSORTED_EVENTS} playSpeed={10} />);

    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(screen.getByRole("button", { name: "Pause" })).toBeTruthy();

    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByText("2 / 3")).toBeTruthy();
    expect(screen.getByText(/event_id: event-middle/)).toBeTruthy();

    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByText("3 / 3")).toBeTruthy();
    expect(screen.getByText(/event_id: event-late/)).toBeTruthy();

    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByRole("button", { name: "Play" })).toBeTruthy();
    expect(screen.getByText("3 / 3")).toBeTruthy();
  });

  it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY])(
    "falls back to the default playback speed for invalid playSpeed %s",
    async (playSpeed) => {
      vi.useFakeTimers();
      render(<TrajectoryReplay events={UNSORTED_EVENTS} playSpeed={playSpeed} />);

      fireEvent.click(screen.getByRole("button", { name: "Play" }));
      act(() => {
        vi.advanceTimersByTime(499);
      });
      expect(screen.getByText("1 / 3")).toBeTruthy();

      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(screen.getByText("2 / 3")).toBeTruthy();
      expect(screen.getByText(/event_id: event-middle/)).toBeTruthy();
    },
  );

  it("restarts at the first sorted event", () => {
    render(<TrajectoryReplay events={UNSORTED_EVENTS} />);

    fireEvent.change(screen.getByRole("slider"), { target: { value: "2" } });
    expect(screen.getByText(/event_id: event-late/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "⏮ Restart" }));

    expect(screen.getByText("1 / 3")).toBeTruthy();
    expect(screen.getByText(/event_id: event-early/)).toBeTruthy();
  });
});
