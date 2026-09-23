/**
 * MascotStation.dock.test.tsx — the mascot's station is reserved chrome
 * (design wave 3; the 2026-09-23 veto "MascotStation covers content and
 * captures taps at 390").
 *
 * The station used to be seeded at (88, viewport-160): over the working area,
 * where it covered inputs, cards and the breadcrumb. The dock now reserves a
 * 64px slot ([data-mascot-station]); the mascot seats itself there on mount
 * and after a resize, until the operator drags it somewhere else (the
 * ratified drag-to-re-station contract is unchanged).
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { MascotStation } from "./MascotStation";
import { useWorkspace } from "../workspace/WorkspaceStore";

let slotRect = { left: 1216, top: 736, width: 64, height: 64 };

function Slot() {
  return (
    <span
      data-mascot-station
      ref={(el) => {
        if (el)
          el.getBoundingClientRect = () =>
            ({ ...slotRect, right: slotRect.left + slotRect.width, bottom: slotRect.top + slotRect.height, x: slotRect.left, y: slotRect.top, toJSON: () => ({}) }) as DOMRect;
      }}
    />
  );
}

/** Where the mascot is drawn, whether it is placed by left/top or transform. */
function drawnAt(el: HTMLElement): { x: number; y: number } {
  const t = el.style.transform.match(/translate\((-?[\d.]+)px,\s*(-?[\d.]+)px\)/);
  if (t) return { x: Number(t[1]) + (parseFloat(el.style.left) || 0), y: Number(t[2]) + (parseFloat(el.style.top) || 0) };
  return { x: parseFloat(el.style.left), y: parseFloat(el.style.top) };
}

function mount() {
  return render(
    <MemoryRouter>
      <Slot />
      <MascotStation />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  useWorkspace.getState().reset();
  slotRect = { left: 1216, top: 736, width: 64, height: 64 };
  Object.defineProperty(window, "innerWidth", { value: 1280, configurable: true });
  Object.defineProperty(window, "innerHeight", { value: 800, configurable: true });
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (q: string) => ({
      matches: q.includes("reduce"),
      media: q,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
  const proto = HTMLElement.prototype as unknown as Record<string, unknown>;
  proto.setPointerCapture = () => {};
  proto.releasePointerCapture = () => {};
  proto.hasPointerCapture = () => false;
});

afterEach(() => cleanup());

describe("the mascot sits in the dock's reserved station", () => {
  it("seats itself on the slot at mount, not over the working area", () => {
    mount();
    expect(drawnAt(screen.getByTestId("brain-mascot"))).toEqual({ x: 1216, y: 736 });
  });

  it("follows the slot when the viewport changes (390 px phone dock)", () => {
    mount();
    slotRect = { left: 326, top: 780, width: 64, height: 64 };
    Object.defineProperty(window, "innerWidth", { value: 390, configurable: true });
    Object.defineProperty(window, "innerHeight", { value: 844, configurable: true });
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });
    expect(drawnAt(screen.getByTestId("brain-mascot"))).toEqual({ x: 326, y: 780 });
  });

  it("stays where the operator drags it (the ratified re-station contract)", () => {
    mount();
    const m = screen.getByTestId("brain-mascot");
    fireEvent.pointerDown(m, { clientX: 1240, clientY: 760, pointerId: 1 });
    fireEvent.pointerMove(m, { clientX: 1040, clientY: 560, pointerId: 1 });
    fireEvent.pointerUp(m, { clientX: 1040, clientY: 560, pointerId: 1 });
    const dropped = drawnAt(m);
    expect(dropped).not.toEqual({ x: 1216, y: 736 });
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });
    expect(drawnAt(m)).toEqual(dropped);
  });
});
