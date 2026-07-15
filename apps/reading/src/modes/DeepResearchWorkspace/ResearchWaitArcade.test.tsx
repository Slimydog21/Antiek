import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { createRef, useEffect, useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const createCartridge = vi.hoisted(() => vi.fn());
const teardown = vi.hoisted(() => vi.fn());

vi.mock("./ResearchWaitArcadeGame", () => ({
  default: () => {
    createCartridge();
    const canvasRef = useRef<HTMLCanvasElement>(null);
    useEffect(() => {
      canvasRef.current?.focus();
    }, []);
    return (
      <canvas
        ref={canvasRef}
        data-testid="research-wait-arcade-canvas"
        role="application"
        tabIndex={0}
      />
    );
  },
}));

import ResearchWaitArcade from "./ResearchWaitArcade";
import { isStationInstrumentSuspended } from "../../werner/stationInstrumentSuspension";

function cartridge() {
  return {
    id: "paperclip-zombies",
    meta: { title: "Paperclip Zombies", blurb: "", style: "zombies-arcade" },
    init: vi.fn(),
    update: vi.fn(),
    render: vi.fn(),
    teardown,
  };
}

function Host({ episodeId = "session:1", after = 8_000 }) {
  const returnFocusRef = createRef<HTMLHeadingElement>();
  return (
    <>
      <h2 ref={returnFocusRef} tabIndex={-1}>
        Research monitor
      </h2>
      <ResearchWaitArcade
        episodeId={episodeId}
        activeResearchCount={2}
        offerAfterMs={after}
        returnFocusRef={returnFocusRef}
      />
    </>
  );
}

function ConditionalHost({ visible }: { visible: boolean }) {
  const returnFocusRef = useRef<HTMLHeadingElement>(null);
  return (
    <>
      <h2 ref={returnFocusRef} tabIndex={-1}>
        Research monitor
      </h2>
      {visible && (
        <ResearchWaitArcade
          episodeId="session:terminal"
          activeResearchCount={1}
          offerAfterMs={0}
          returnFocusRef={returnFocusRef}
        />
      )}
    </>
  );
}

function LeavingHost({ visible }: { visible: boolean }) {
  const returnFocusRef = useRef<HTMLHeadingElement>(null);
  return (
    <>
      <h2 ref={returnFocusRef} tabIndex={-1}>
        Research monitor
      </h2>
      <button type="button">Redirect research</button>
      {visible && (
        <ResearchWaitArcade
          episodeId="session:1"
          activeResearchCount={1}
          offerAfterMs={0}
          returnFocusRef={returnFocusRef}
        />
      )}
    </>
  );
}

beforeEach(() => {
  vi.useFakeTimers();
  createCartridge.mockReset();
  teardown.mockReset();
  createCartridge.mockImplementation(cartridge);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("ResearchWaitArcade", () => {
  it("does not construct or flash a game before the exact offer threshold", () => {
    render(<Host after={8_000} />);
    act(() => vi.advanceTimersByTime(7_999));
    expect(screen.queryByTestId("research-wait-arcade")).toBeNull();
    expect(createCartridge).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(1));
    expect(
      screen.getByRole("button", { name: "Play while waiting" }),
    ).toBeTruthy();
    expect(createCartridge).not.toHaveBeenCalled();
  });

  it("constructs only after explicit Play and does not focus before activation", async () => {
    render(<Host after={0} />);
    act(() => vi.runOnlyPendingTimers());
    expect(document.activeElement).toBe(document.body);
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Play while waiting" }),
      );
    });
    const canvas = screen.getByTestId("research-wait-arcade-canvas");
    expect(createCartridge).toHaveBeenCalledTimes(1);
    expect(canvas).toBe(document.activeElement);
    expect(isStationInstrumentSuspended()).toBe(true);
  });

  it.each(["Escape", "button"])(
    "exits with %s and restores focus to the visible Play control",
    (exitKind) => {
      render(<Host after={0} />);
      act(() => vi.runOnlyPendingTimers());
      fireEvent.click(
        screen.getByRole("button", { name: "Play while waiting" }),
      );
      if (exitKind === "Escape") {
        fireEvent.keyDown(screen.getByTestId("research-wait-arcade-canvas"), {
          key: "Escape",
        });
      } else {
        fireEvent.click(screen.getByRole("button", { name: "Exit game" }));
      }
      act(() => vi.runAllTicks());
      expect(screen.queryByTestId("research-wait-arcade-canvas")).toBeNull();
      expect(screen.getByRole("button", { name: "Play while waiting" })).toBe(
        document.activeElement,
      );
      expect(isStationInstrumentSuspended()).toBe(false);
    },
  );

  it("resets opt-in and timer when the episode identity changes", () => {
    const { rerender } = render(<Host episodeId="same:1" after={0} />);
    act(() => vi.runOnlyPendingTimers());
    fireEvent.click(screen.getByRole("button", { name: "Play while waiting" }));
    expect(createCartridge).toHaveBeenCalledTimes(1);

    rerender(<Host episodeId="same:2" after={8_000} />);
    expect(isStationInstrumentSuspended()).toBe(false);
    expect(screen.queryByTestId("research-wait-arcade")).toBeNull();
    expect(screen.queryByTestId("research-wait-arcade-canvas")).toBeNull();
    act(() => vi.advanceTimersByTime(8_000));
    expect(
      screen.getByRole("button", { name: "Play while waiting" }),
    ).toBeTruthy();
  });

  it("creates a fresh cartridge across repeated Play and Exit cycles", () => {
    render(<Host after={0} />);
    act(() => vi.runOnlyPendingTimers());
    fireEvent.click(screen.getByRole("button", { name: "Play while waiting" }));
    fireEvent.click(screen.getByRole("button", { name: "Exit game" }));
    act(() => vi.runAllTicks());
    fireEvent.click(screen.getByRole("button", { name: "Play while waiting" }));
    expect(createCartridge).toHaveBeenCalledTimes(2);
  });

  it("returns focus to the stable monitor heading when completion removes focused gameplay", async () => {
    const { rerender } = render(<ConditionalHost visible />);
    act(() => vi.runOnlyPendingTimers());
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Play while waiting" }),
      );
    });
    rerender(<ConditionalHost visible={false} />);
    expect(isStationInstrumentSuspended()).toBe(false);
    expect(screen.getByRole("heading", { name: "Research monitor" })).toBe(
      document.activeElement,
    );
  });

  it("does not steal focus when completion follows a deliberate workspace move", () => {
    const { rerender } = render(<LeavingHost visible />);
    act(() => vi.runOnlyPendingTimers());
    fireEvent.click(screen.getByRole("button", { name: "Play while waiting" }));
    const redirect = screen.getByRole("button", { name: "Redirect research" });
    redirect.focus();

    rerender(<LeavingHost visible={false} />);

    expect(redirect).toBe(document.activeElement);
  });

  it("does not capture Escape from a workspace input outside the game", () => {
    render(
      <div>
        <input aria-label="redirect research" />
        <Host after={0} />
      </div>,
    );
    act(() => vi.runOnlyPendingTimers());
    fireEvent.click(screen.getByRole("button", { name: "Play while waiting" }));
    const input = screen.getByRole("textbox", { name: "redirect research" });
    input.focus();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.getByTestId("research-wait-arcade-canvas")).toBeTruthy();
  });

  it("exposes responsive containment and no raw runtime image", () => {
    render(<Host after={0} />);
    act(() => vi.runOnlyPendingTimers());
    const host = screen.getByTestId("research-wait-arcade");
    expect(host.className).toContain("research-wait-arcade");
    expect(host.querySelector("img")).toBeNull();
  });
});
