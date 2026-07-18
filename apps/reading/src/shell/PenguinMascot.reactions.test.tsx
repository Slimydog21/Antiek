import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { emitLivingTvHostBeat } from "../arcade/host/livingTvHostEmit";
import { emitWernerExperience, WERNER_EXPERIENCE_EVENT } from "../werner";
import { useWorkspace } from "../workspace/WorkspaceStore";
import { PenguinMascot } from "./PenguinMascot";

beforeEach(() => {
  useWorkspace.getState().reset();
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("PenguinMascot product reactions", () => {
  it("does not fabricate an idle edge on its first animation frame", () => {
    const frames: FrameRequestCallback[] = [];
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      frames.push(callback);
      return frames.length;
    });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
    const listener = vi.fn();
    window.addEventListener(WERNER_EXPERIENCE_EVENT, listener);

    render(
      <MemoryRouter>
        <PenguinMascot />
      </MemoryRouter>,
    );
    const firstFrames = frames.splice(0);
    act(() => firstFrames.forEach((callback) => callback(0)));

    expect(listener).not.toHaveBeenCalled();
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener);
  });

  it("does not treat hidden-tab elapsed time as a fresh idle edge", () => {
    let now = 0;
    vi.spyOn(performance, "now").mockImplementation(() => now);
    const frames: FrameRequestCallback[] = [];
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      frames.push(callback);
      return frames.length;
    });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
    const hiddenDescriptor = Object.getOwnPropertyDescriptor(document, "hidden");
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: false,
    });
    const listener = vi.fn();
    window.addEventListener(WERNER_EXPERIENCE_EVENT, listener);

    render(
      <MemoryRouter>
        <PenguinMascot />
      </MemoryRouter>,
    );
    act(() =>
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 100, clientY: 100 }),
      ),
    );
    act(() => frames.splice(0).forEach((callback) => callback(now)));

    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: true,
    });
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    now = 3_000;
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: false,
    });
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    act(() => frames.splice(0).forEach((callback) => callback(now)));

    expect(listener).not.toHaveBeenCalled();
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener);
    if (hiddenDescriptor) {
      Object.defineProperty(document, "hidden", hiddenDescriptor);
    } else {
      Reflect.deleteProperty(document, "hidden");
    }
  });

  it("translates real product experiences through its single stage", () => {
    render(
      <MemoryRouter initialEntries={["/brainstorm"]}>
        <PenguinMascot />
      </MemoryRouter>,
    );
    const mascot = screen.getByTestId("penguin-mascot");
    expect(mascot.getAttribute("data-werner-emote")).toBe("none");

    act(() => emitWernerExperience("highlight"));
    expect(mascot.getAttribute("data-werner-emote")).toBe("curious");

    act(() => emitWernerExperience("deep_research_complete"));
    expect(mascot.getAttribute("data-werner-emote")).toBe("happy");
  });

  it("receives arcade living-TV host beats on the same stage path as product bus", () => {
    // Arcade hosts inject emitLivingTvHostBeat without importing reactionBus.
    // The mascot must still animate as the asynchronous TV show at Antiek.
    render(
      <MemoryRouter initialEntries={["/brainstorm"]}>
        <PenguinMascot />
      </MemoryRouter>,
    );
    const mascot = screen.getByTestId("penguin-mascot");
    expect(mascot.getAttribute("data-werner-emote")).toBe("none");

    act(() => emitLivingTvHostBeat("highlight"));
    expect(mascot.getAttribute("data-werner-emote")).toBe("curious");

    act(() => emitLivingTvHostBeat("piece_started"));
    expect(mascot.getAttribute("data-werner-emote")).toBe("happy");
  });

  it("removes the shared reaction listener on unmount", () => {
    const remove = vi.spyOn(window, "removeEventListener");
    const view = render(
      <MemoryRouter>
        <PenguinMascot />
      </MemoryRouter>,
    );

    view.unmount();

    expect(remove).toHaveBeenCalledWith(
      WERNER_EXPERIENCE_EVENT,
      expect.any(Function),
    );
  });
});
