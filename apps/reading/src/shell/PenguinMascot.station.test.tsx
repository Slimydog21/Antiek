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
 *   (2) NO CURSOR INSTRUMENT — the fishing rod, the bait line and the
 *       never-catch gag were REMOVED at the operator's directive (2026-08-13);
 *       the station stays calm for any pointer state.
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

import { PenguinMascot } from "./PenguinMascot";
import { useWorkspace } from "../workspace/WorkspaceStore";

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
    // This suite pins the calm station behavior. `/` is now a knowledge-work
    // route and intentionally selects research-lens, so use a utility route.
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

  it("stays calm for any pointer state (no fishing gag, no bait class)", () => {
    const { container } = mount();
    const bob = container.querySelector('[data-testid="penguin-mascot"] > span');
    expect(bob).toBeTruthy();

    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 400, clientY: 300, bubbles: true }),
      );
    });
    act(() => {
      vi.advanceTimersByTime(20000);
    });
    expect(container.querySelector(".werner-fishing")).toBeNull();
    expect(bob?.className).not.toContain("werner-fishing");

    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 405, clientY: 305, bubbles: true }),
      );
    });
    act(() => {
      vi.advanceTimersByTime(64);
    });
    expect(container.querySelector(".werner-fishing")).toBeNull();
  });

it("does not wander off on its own (fixed station)", () => {
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
