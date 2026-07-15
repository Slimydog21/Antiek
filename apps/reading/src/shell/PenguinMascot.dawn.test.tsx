/**
 * PenguinMascot.dawn.test.tsx — SPR-22 dawn waking beat acceptance.
 *
 * Verifies:
 *  - One cue is consumed at most once.
 *  - Normal dawn beat: shows waking artwork for the authored duration.
 *  - Reduced motion: renders the same semantic beat statically.
 *  - Preempted cue (product emote, drag): consumed, never replayed.
 *  - One visible Werner pose (base rig hidden while beat active).
 *  - Timer cleared on unmount (no stray callbacks).
 */
import {
  afterAll,
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../werner/iceFishingFlags", () => ({
  wernerIceFishingCursor: true,
}));

import { PenguinMascot } from "./PenguinMascot";
import type { SceneMomentCue } from "../scene/useDawnCue";
import { useWorkspace } from "../workspace/WorkspaceStore";
import {
  emitWernerExperience,
  STATION_LONG_REST_MS,
  STATION_WAKE_MS,
} from "../werner";
import { acquireStationInstrumentSuspension } from "../werner/stationInstrumentSuspension";

const s = () => useWorkspace.getState();

const proto = window.HTMLElement.prototype as unknown as Record<string, unknown>;
const ORIG = {
  setPointerCapture: proto.setPointerCapture,
  releasePointerCapture: proto.releasePointerCapture,
  hasPointerCapture: proto.hasPointerCapture,
  matchMedia: (window as unknown as { matchMedia?: unknown }).matchMedia,
};

beforeEach(() => {
  s().reset();
  vi.useFakeTimers();
  proto.setPointerCapture = vi.fn();
  proto.releasePointerCapture = vi.fn();
  proto.hasPointerCapture = vi.fn(() => false);
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (q: string) => ({
      matches: false,
      media: q,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    }),
  });
  Object.defineProperty(window, "innerWidth", {
    value: 1200,
    configurable: true,
  });
  Object.defineProperty(window, "innerHeight", {
    value: 800,
    configurable: true,
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

afterAll(() => {
  proto.setPointerCapture = ORIG.setPointerCapture;
  proto.releasePointerCapture = ORIG.releasePointerCapture;
  proto.hasPointerCapture = ORIG.hasPointerCapture;
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: ORIG.matchMedia,
  });
});

function mount(props: {
  sceneBeat?: SceneMomentCue | null;
  onDawnBeatEnd?: (sequence: number) => void;
} = {}) {
  const ui = (next = props) => (
    <MemoryRouter initialEntries={["/settings"]}>
      <Routes>
        <Route
          path="*"
          element={
            <PenguinMascot
              sceneBeat={next.sceneBeat}
              onDawnBeatEnd={next.onDawnBeatEnd}
            />
          }
        />
      </Routes>
    </MemoryRouter>
  );
  const view = render(ui());
  return { ...view, rerenderMascot: (next = props) => view.rerender(ui(next)) };
}

const dawnCue = (sequence = 1): SceneMomentCue => ({
  sequence,
  moment: "daybreak",
});

async function advanceFrames(totalMs: number) {
  await act(async () => {
    vi.advanceTimersByTime(totalMs);
    await Promise.resolve();
  });
}

describe("PenguinMascot — dawn waking beat (SPR-22)", () => {
  it("normal dawn beat: shows waking artwork for the authored duration", async () => {
    const { container } = mount({ sceneBeat: dawnCue() });
    await advanceFrames(16);
    expect(
      container.querySelector('[data-werner-waking="true"]'),
      "waking artwork must be visible when dawn beat fires",
    ).toBeTruthy();
    // The base rig should be hidden while the beat is active.
    const rigSpan = container.querySelector(
      '[data-testid="penguin-mascot"] > span > span:first-child',
    );
    expect(rigSpan?.getAttribute("style")).toContain("visibility: hidden");

    await advanceFrames(STATION_WAKE_MS + 32);
    expect(
      container.querySelector('[data-werner-waking="true"]'),
      "waking artwork must clear after the beat duration",
    ).toBeNull();
  });

  it("calls onDawnBeatEnd exactly once when the beat completes", async () => {
    const onEnd = vi.fn();
    mount({ sceneBeat: dawnCue(), onDawnBeatEnd: onEnd });
    await advanceFrames(16);
    expect(onEnd).not.toHaveBeenCalled();
    await advanceFrames(STATION_WAKE_MS + 32);
    expect(onEnd).toHaveBeenCalledTimes(1);
    expect(onEnd).toHaveBeenCalledWith(1);
  });

  it("preempts when product emote fires during dawn beat", async () => {
    const onEnd = vi.fn();
    const { container } = mount({ sceneBeat: dawnCue(), onDawnBeatEnd: onEnd });
    await advanceFrames(16);
    expect(
      container.querySelector('[data-werner-waking="true"]'),
    ).toBeTruthy();

    act(() => emitWernerExperience("highlight"));
    await advanceFrames(32);
    expect(onEnd).toHaveBeenCalledTimes(1);
    expect(
      container.querySelector('[data-werner-waking="true"]'),
      "waking artwork must clear on preemption",
    ).toBeNull();
  });

  it("preempts when drag starts during dawn beat", async () => {
    const onEnd = vi.fn();
    mount({ sceneBeat: dawnCue(), onDawnBeatEnd: onEnd });
    await advanceFrames(16);
    const el = screen.getByTestId("penguin-mascot") as HTMLButtonElement;

    fireEvent.pointerDown(el, { pointerId: 1, clientX: 88, clientY: 700 });
    await advanceFrames(32);
    expect(onEnd).toHaveBeenCalledTimes(1);
    fireEvent.pointerUp(el, { pointerId: 1 });
  });

  it("reduced motion: renders the same semantic beat statically for the bounded duration", async () => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: (q: string) => ({
        matches: q.includes("prefers-reduced-motion"),
        media: q,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
      }),
    });
    const { container } = mount({ sceneBeat: dawnCue() });
    await advanceFrames(16);
    expect(
      container.querySelector('[data-werner-waking="true"]'),
      "reduced-motion dawn beat must render the waking artwork",
    ).toBeTruthy();
    const wakingEl = container.querySelector('[data-werner-waking="true"]');
    expect(wakingEl?.getAttribute("data-reduced")).toBe("true");
    await advanceFrames(STATION_WAKE_MS + 32);
    expect(
      container.querySelector('[data-werner-waking="true"]'),
    ).toBeNull();
  });

  it("clears dawn timer on unmount (no stray callback)", async () => {
    const onEnd = vi.fn();
    const { unmount } = mount({ sceneBeat: dawnCue(), onDawnBeatEnd: onEnd });
    await advanceFrames(16);
    unmount();
    await advanceFrames(STATION_WAKE_MS + 100);
    expect(onEnd).not.toHaveBeenCalled();
  });

  it("one visible Werner pose: base rig hidden while dawn beat active", async () => {
    const { container } = mount({ sceneBeat: dawnCue() });
    await advanceFrames(16);
    const wakingEls = container.querySelectorAll(
      '[data-werner-waking="true"]',
    );
    expect(wakingEls.length).toBe(1);
  });

  it("dawn beat and long-rest waking have separate state", async () => {
    const { container } = mount({ sceneBeat: dawnCue() });
    await advanceFrames(16);
    expect(
      container.querySelector('[data-werner-waking="true"]'),
    ).toBeTruthy();
    expect(
      container.querySelector('[data-werner-authored-pose="sleeping"]'),
      "dawn beat must not trigger long-rest sleeping",
    ).toBeNull();
    await advanceFrames(STATION_WAKE_MS + 32);
    expect(
      container.querySelector('[data-werner-waking="true"]'),
    ).toBeNull();
  });

  it("does not replay a consumed sequence on rerender", async () => {
    const onEnd = vi.fn();
    const cue = dawnCue();
    const view = mount({ sceneBeat: cue, onDawnBeatEnd: onEnd });
    await advanceFrames(STATION_WAKE_MS + 32);
    view.rerenderMascot({ sceneBeat: cue, onDawnBeatEnd: onEnd });
    await advanceFrames(32);
    expect(onEnd).toHaveBeenCalledTimes(1);
    expect(view.container.querySelector('[data-werner-waking="true"]')).toBeNull();
  });

  it("rejects a cue while a product surface owns the station", async () => {
    const release = acquireStationInstrumentSuspension("dawn-test");
    const onEnd = vi.fn();
    const { container } = mount({ sceneBeat: dawnCue(), onDawnBeatEnd: onEnd });
    await advanceFrames(16);
    expect(onEnd).toHaveBeenCalledWith(1);
    expect(container.querySelector('[data-werner-waking="true"]')).toBeNull();
    release();
  });

  it("preempts when a product surface acquires the station", async () => {
    const onEnd = vi.fn();
    const { container } = mount({ sceneBeat: dawnCue(), onDawnBeatEnd: onEnd });
    await advanceFrames(16);
    const release = acquireStationInstrumentSuspension("dawn-test");
    await advanceFrames(16);
    expect(onEnd).toHaveBeenCalledWith(1);
    expect(container.querySelector('[data-werner-waking="true"]')).toBeNull();
    release();
  });

  it("true long-rest waking preempts the dawn beat", async () => {
    const onEnd = vi.fn();
    const view = mount({ onDawnBeatEnd: onEnd });
    await advanceFrames(32);
    await advanceFrames(STATION_LONG_REST_MS + 16);
    view.rerenderMascot({ sceneBeat: dawnCue(), onDawnBeatEnd: onEnd });
    await advanceFrames(16);
    fireEvent.keyDown(window, { key: "a" });
    await advanceFrames(16);
    expect(onEnd).toHaveBeenCalledWith(1);
    expect(
      screen.getByTestId("penguin-mascot").getAttribute("data-werner-rest-phase"),
    ).toBe("waking");
  });
});
