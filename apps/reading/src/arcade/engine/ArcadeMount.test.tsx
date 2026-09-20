import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ArcadeMount } from "./ArcadeMount";
import type { Cartridge } from "./types";

function cartridge(): Cartridge {
  return {
    id: "mount-test",
    meta: { title: "Test cartridge", blurb: "", style: "demo" },
    init: vi.fn(),
    update: vi.fn(),
    render: vi.fn(),
    teardown: vi.fn(),
  };
}

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    {} as CanvasRenderingContext2D,
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ArcadeMount input and accessibility boundary", () => {
  it("is focusable, described, and scopes game keys to its canvas", () => {
    const cart = cartridge();
    render(<ArcadeMount cartridge={cart} reducedMotion />);
    const canvas = screen.getByRole("application", { name: "Test cartridge" });

    expect(canvas.getAttribute("tabindex")).toBe("0");
    const description = document.getElementById(
      canvas.getAttribute("aria-describedby") ?? "",
    );
    expect(description?.textContent).toMatch(/Space or Enter to start/);

    fireEvent.keyDown(window, { key: "Enter" });
    expect(cart.update).not.toHaveBeenCalled();

    const propagated = fireEvent.keyDown(canvas, { key: "Enter" });
    expect(propagated).toBe(false);
    expect(cart.update).toHaveBeenCalledTimes(1);
    expect(
      (cart.update as ReturnType<typeof vi.fn>).mock.calls[0]?.[1].keysPressed,
    ).toEqual(new Set(["Enter"]));
  });

  it("scales responsive pointer coordinates into logical canvas pixels", () => {
    const cart = cartridge();
    render(
      <ArcadeMount cartridge={cart} width={400} height={200} reducedMotion />,
    );
    const canvas = screen.getByRole("application", { name: "Test cartridge" });
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({
      x: 10,
      y: 20,
      left: 10,
      top: 20,
      right: 210,
      bottom: 120,
      width: 200,
      height: 100,
      toJSON: () => ({}),
    });
    Object.assign(canvas, {
      setPointerCapture: vi.fn(),
      hasPointerCapture: vi.fn(() => true),
      releasePointerCapture: vi.fn(),
    });

    fireEvent.pointerDown(canvas, {
      pointerId: 7,
      clientX: 110,
      clientY: 70,
    });

    const input = (cart.update as ReturnType<typeof vi.fn>).mock.calls[0]?.[1];
    expect(input.pointer).toEqual({ x: 200, y: 100 });
    expect(input.pointerPressed).toBe(true);
    expect(document.activeElement).toBe(canvas);
  });

  it("tears down once and releases an active pointer capture", () => {
    const cart = cartridge();
    const view = render(<ArcadeMount cartridge={cart} reducedMotion />);
    const canvas = screen.getByRole("application", { name: "Test cartridge" });
    const releasePointerCapture = vi.fn();
    Object.assign(canvas, {
      setPointerCapture: vi.fn(),
      hasPointerCapture: vi.fn(() => true),
      releasePointerCapture,
    });
    fireEvent.pointerDown(canvas, { pointerId: 4, clientX: 1, clientY: 1 });

    view.unmount();

    expect(releasePointerCapture).toHaveBeenCalledWith(4);
    expect(cart.teardown).toHaveBeenCalledTimes(1);
  });
});
