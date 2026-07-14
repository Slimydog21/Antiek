/**
 * PenguinMascot.station.test.tsx — the fixed-station behaviours that need the
 * WERNER-ICE flag ON and a mounted rAF (2026-07-02 rework).
 *
 * This REPLACES the deleted PenguinMascot.iceFishing.integration.test.tsx,
 * whose central pin was "a bare pointermove MOVES the penguin" (the reel). That
 * behaviour is exactly what the operator removed, so its inverse is now the
 * load-bearing regression guard:
 *
 *   (1) THE PENGUIN DOES NOT FOLLOW THE CURSOR — a pointermove (anywhere, any
 *       distance) leaves Werner's position untouched. This is the whole ask.
 *   (2) THE CURSOR IS THE BAIT — when the pointer goes idle Werner runs his own
 *       -hole never-catch gag (`werner-fishing`); the moment the pointer moves
 *       again the gag stands down (the line to the cursor-bait takes over).
 *
 * Flag mocked ON (the production default) so the ice-fishing experience is live.
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
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../werner/iceFishingFlags", () => ({
  wernerIceFishingCursor: true,
}));

import { PenguinMascot } from "./PenguinMascot";
import { useWorkspace } from "../workspace/WorkspaceStore";
import { emitWernerExperience } from "../werner";
import { STATION_LONG_REST_MS, STATION_WAKE_MS } from "../werner";
import { acquireStationInstrumentSuspension } from "../werner/stationInstrumentSuspension";

const s = () => useWorkspace.getState();

const ORIG_matchMedia = (window as unknown as { matchMedia?: unknown })
  .matchMedia;

beforeEach(() => {
  s().reset();
  vi.useFakeTimers();
  // Motion allowed (reduce = false) so the station gag + rAF are live.
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
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: ORIG_matchMedia,
  });
});

function mount() {
  return render(
    // This suite pins the ice-fishing station behavior specifically. `/` is
    // now a knowledge-work route and intentionally selects research-lens, so
    // use a utility route where ice fishing remains the deterministic default.
    <MemoryRouter initialEntries={["/settings"]}>
      <Routes>
        <Route path="*" element={<PenguinMascot />} />
      </Routes>
    </MemoryRouter>,
  );
}

/** Advance a batch of animation frames (~16ms each) under fake timers, driving
 *  both the mascot's gag rAF and useMouseFollow's sampling. */
function advanceFrames(totalMs: number) {
  act(() => {
    vi.advanceTimersByTime(totalMs);
  });
}

describe("PenguinMascot — the fixed station (flag on)", () => {
  it("keeps fishing as short idle, then runs one persistent sleep-to-wake episode", async () => {
    const { container } = mount();
    advanceFrames(2_600);
    expect(container.querySelector(".werner-fishing")).toBeTruthy();
    expect(
      container.querySelector('[data-werner-authored-pose="sleeping"]'),
    ).toBeNull();

    advanceFrames(STATION_LONG_REST_MS - 2_600 + 32);
    expect(container.querySelector(".werner-fishing")).toBeNull();
    expect(
      container.querySelector('[data-werner-authored-pose="sleeping"]'),
    ).toBeTruthy();

    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointerdown", { clientX: 100, clientY: 100 }),
      );
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(
      container.querySelector('[data-werner-authored-pose="waking"]'),
    ).toBeTruthy();
    expect(
      container.querySelector('[data-werner-authored-pose="sleeping"]'),
    ).toBeNull();
    advanceFrames(STATION_WAKE_MS);
    expect(
      container.querySelector('[data-werner-authored-pose="waking"]'),
    ).toBeNull();
  });

  it("treats arcade play as suspension and requires a fresh rest epoch", () => {
    const { container } = mount();
    advanceFrames(STATION_LONG_REST_MS - 100);
    let release = () => {};
    act(() => {
      release = acquireStationInstrumentSuspension("test-arcade");
    });
    advanceFrames(200);
    expect(screen.getByTestId("penguin-mascot").dataset.wernerRestPhase).toBe(
      "suspended",
    );
    act(() => release());
    advanceFrames(STATION_LONG_REST_MS - 32);
    expect(
      container.querySelector('[data-werner-authored-pose="sleeping"]'),
    ).toBeNull();
    advanceFrames(64);
    expect(
      container.querySelector('[data-werner-authored-pose="sleeping"]'),
    ).toBeTruthy();
  });

  it("does not accrue hidden-tab time or wake merely on visibility return", () => {
    const { container } = mount();
    advanceFrames(STATION_LONG_REST_MS - 100);
    Object.defineProperty(document, "hidden", {
      value: true,
      configurable: true,
    });
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    advanceFrames(10_000);
    Object.defineProperty(document, "hidden", {
      value: false,
      configurable: true,
    });
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    advanceFrames(32);
    expect(screen.getByTestId("penguin-mascot").dataset.wernerRestPhase).toBe(
      "active",
    );
    expect(
      container.querySelector('[data-werner-authored-pose="waking"]'),
    ).toBeNull();
    expect(
      container.querySelector('[data-werner-authored-pose="sleeping"]'),
    ).toBeNull();
  });

  it("lets a foreground product emote preempt persistent sleep", () => {
    const { container } = mount();
    advanceFrames(STATION_LONG_REST_MS + 32);
    expect(
      container.querySelector('[data-werner-authored-pose="sleeping"]'),
    ).toBeTruthy();
    act(() => emitWernerExperience("highlight"));
    advanceFrames(32);
    expect(screen.getByTestId("penguin-mascot").dataset.wernerEmote).toBe(
      "curious",
    );
    expect(screen.getByTestId("penguin-mascot").dataset.wernerRestPhase).toBe(
      "suspended",
    );
    expect(
      container.querySelector('[data-werner-authored-pose="sleeping"]'),
    ).toBeNull();
  });

  it("observes keyboard presence without swallowing the downstream event", () => {
    const downstream = vi.fn();
    window.addEventListener("keydown", downstream, true);
    const { container } = mount();
    advanceFrames(STATION_LONG_REST_MS + 32);
    act(() =>
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" })),
    );
    expect(downstream).toHaveBeenCalledOnce();
    expect(screen.getByTestId("penguin-mascot").dataset.wernerRestPhase).toBe(
      "waking",
    );
    expect(container.querySelector("[data-werner-authored-pose]")).toBeTruthy();
    window.removeEventListener("keydown", downstream, true);
  });

  it("keeps one accessible project control and decorative lifecycle art", () => {
    const { container } = mount();
    advanceFrames(STATION_LONG_REST_MS + 32);
    expect(
      screen.getAllByRole("button", {
        name: "Project — click to float the project tree, double-click to open",
      }),
    ).toHaveLength(1);
    expect(screen.queryAllByRole("img")).toHaveLength(0);
    expect(
      container.querySelectorAll('img:not([aria-hidden="true"])'),
    ).toHaveLength(0);
  });

  it("never enters decorative long rest under reduced motion", () => {
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
    const { container } = mount();
    advanceFrames(STATION_LONG_REST_MS + 1_000);
    expect(screen.getByTestId("penguin-mascot").dataset.wernerRestPhase).toBe(
      "suspended",
    );
    expect(
      container.querySelector('[data-werner-authored-pose="sleeping"]'),
    ).toBeNull();
    expect(
      container.querySelector('[data-werner-authored-pose="waking"]'),
    ).toBeNull();
  });

  it("does NOT follow the cursor — a pointermove leaves Werner's position untouched", () => {
    mount();
    const el = screen.getByTestId("penguin-mascot") as HTMLButtonElement;
    const startLeft = parseFloat(el.style.left);
    const startTop = parseFloat(el.style.top);

    // Fire pointer moves all over the viewport, then let many frames run.
    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", {
          clientX: 900,
          clientY: 120,
          bubbles: true,
        }),
      );
    });
    advanceFrames(1200);
    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", {
          clientX: 40,
          clientY: 700,
          bubbles: true,
        }),
      );
    });
    advanceFrames(1200);

    // The reel is gone: the mascot never chases the pointer. Fixed station.
    expect(parseFloat(el.style.left)).toBe(startLeft);
    expect(parseFloat(el.style.top)).toBe(startTop);
  });

  it("runs the own-hole gag when the pointer is idle, and drops it when the pointer moves", () => {
    const { container } = mount();
    const bob = container.querySelector(
      '[data-testid="penguin-mascot"] > span',
    );
    expect(bob).toBeTruthy();

    // Make one move, then leave the pointer still well past POINTER_IDLE_MS
    // (2000ms) → the gag takes over (own-hole never-catch, cursor at rest).
    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", {
          clientX: 400,
          clientY: 300,
          bubbles: true,
        }),
      );
    });
    advanceFrames(2600);
    expect(
      container.querySelector(".werner-fishing"),
      "pointer idle → the own-hole fishing gag owns Werner",
    ).toBeTruthy();
    expect(
      screen.getByTestId("penguin-mascot").getAttribute("data-werner-emote"),
      "pointer idle has one owner and does not also mount sleeping",
    ).toBe("none");

    // Move again → the gag stands down within a frame. (That the cursor-line
    // then TAKES OVER is a WernerFishingLayer concern, covered directly in
    // WernerFishingLayer.test.tsx — this suite only owns the mascot's gag gate.)
    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", {
          clientX: 405,
          clientY: 305,
          bubbles: true,
        }),
      );
    });
    advanceFrames(64);
    expect(
      container.querySelector(".werner-fishing"),
      "pointer active → the own-hole gag stands down",
    ).toBeNull();
  });

  it("yields ambient ownership to a product emote, then resumes idle fishing", () => {
    const { container } = mount();
    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", {
          clientX: 400,
          clientY: 300,
          bubbles: true,
        }),
      );
    });
    advanceFrames(2600);
    expect(container.querySelector(".werner-fishing")).toBeTruthy();

    act(() => emitWernerExperience("highlight"));
    advanceFrames(32);
    expect(container.querySelector(".werner-fishing")).toBeNull();
    expect(
      screen.getByTestId("penguin-mascot").getAttribute("data-werner-emote"),
    ).toBe("curious");

    advanceFrames(1200 + 32);
    expect(
      screen.getByTestId("penguin-mascot").getAttribute("data-werner-emote"),
    ).toBe("none");
    // React commits the cleared emote at the end of the timer act; the next
    // ambient frame observes that committed foreground state.
    advanceFrames(32);
    expect(container.querySelector(".werner-fishing")).toBeTruthy();
  });

  it("does not wander off on its own even with the flag on (fixed station)", () => {
    mount();
    const el = screen.getByTestId("penguin-mascot") as HTMLButtonElement;
    const startLeft = parseFloat(el.style.left);
    const startTop = parseFloat(el.style.top);
    advanceFrames(30000);
    expect(parseFloat(el.style.left)).toBe(startLeft);
    expect(parseFloat(el.style.top)).toBe(startTop);
  });

  // The load-bearing seam DESIGN.md §6 flags: deleting the ambient roam must NOT
  // break directed choreography (waddle-to-button), because strollTo/restGait
  // were re-homed out of the roam effect. Without this pin, a future ref-scope
  // or effect-order regression would make waddleToEl a silent no-op. We drive the
  // opt-in data-werner-target click path (a plain document click → stage.
  // waddleToEl) with a mocked on-screen rect, and assert Werner walks TO the
  // control and then RETURNS to his station.
  it("still waddles to an activated control and returns to his station (choreography seam intact)", () => {
    const { getByText } = render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="*"
            element={
              <>
                <button data-werner-target="hit">Bump me</button>
                <PenguinMascot />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    const target = getByText("Bump me") as HTMLButtonElement;
    // jsdom lays nothing out → getBoundingClientRect is all zeros, which the
    // stage treats as "off-screen/detached → no-op". Give it a real on-screen
    // rect so waddleToEl actually engages.
    target.getBoundingClientRect = () =>
      ({
        left: 600,
        top: 400,
        width: 80,
        height: 40,
        right: 680,
        bottom: 440,
        x: 600,
        y: 400,
        toJSON: () => ({}),
      }) as DOMRect;

    const el = screen.getByTestId("penguin-mascot") as HTMLButtonElement;
    const homeLeft = parseFloat(el.style.left);
    const homeTop = parseFloat(el.style.top);

    // Activate the control → Werner walks OUT to its center (640, 420).
    act(() => {
      fireEvent.click(target);
    });
    expect(parseFloat(el.style.left)).not.toBe(homeLeft);
    expect(parseFloat(el.style.left)).toBeGreaterThan(homeLeft); // toward the button (right)

    // Advance the full excursion: walk (WADDLE_MS=1800) + hit emote (800) +
    // return-home stroll (STATION_RETURN_MS=900). He must be back on station.
    act(() => {
      vi.advanceTimersByTime(1800 + 800 + 900 + 50);
    });
    expect(parseFloat(el.style.left)).toBe(homeLeft);
    expect(parseFloat(el.style.top)).toBe(homeTop);
  });
});
