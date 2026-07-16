import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
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
    expect(description?.textContent).toMatch(
      /Left and Right control Clam Catcher/,
    );

    fireEvent.keyDown(window, { key: "Enter" });
    expect(cart.update).not.toHaveBeenCalled();

    const propagated = fireEvent.keyDown(canvas, { key: "Enter" });
    expect(propagated).toBe(false);
    expect(cart.update).toHaveBeenCalledTimes(1);
    expect(
      (cart.update as ReturnType<typeof vi.fn>).mock.calls[0]?.[1].keysPressed,
    ).toEqual(new Set(["Enter"]));

    const arrowPropagated = fireEvent.keyDown(canvas, { key: "ArrowLeft" });
    expect(arrowPropagated).toBe(false);
    expect(
      (cart.update as ReturnType<typeof vi.fn>).mock.calls[1]?.[1].keysPressed,
    ).toEqual(new Set(["ArrowLeft"]));
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

  it("pauses and resumes the same cartridge without replaying held input", () => {
    const cart = cartridge();
    const view = render(
      <ArcadeMount cartridge={cart} reducedMotion paused={false} />,
    );
    const canvas = screen.getByRole("application", { name: "Test cartridge" });

    fireEvent.keyDown(canvas, { key: "Enter" });
    expect(cart.init).toHaveBeenCalledTimes(1);
    expect(cart.update).toHaveBeenCalledTimes(1);

    view.rerender(<ArcadeMount cartridge={cart} reducedMotion paused />);
    expect(canvas.getAttribute("data-paused")).toBe("true");
    expect(canvas.getAttribute("aria-disabled")).toBe("true");
    fireEvent.keyDown(canvas, { key: "Enter" });
    expect(cart.update).toHaveBeenCalledTimes(1);
    expect(cart.teardown).not.toHaveBeenCalled();

    view.rerender(
      <ArcadeMount cartridge={cart} reducedMotion paused={false} />,
    );
    expect(canvas.hasAttribute("aria-disabled")).toBe(false);
    expect(cart.init).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(canvas, { key: "ArrowLeft" });
    const input = (cart.update as ReturnType<typeof vi.fn>).mock.calls[1]?.[1];
    expect(input.keysPressed).toEqual(new Set(["ArrowLeft"]));
    expect(input.keysDown).toEqual(new Set(["ArrowLeft"]));

    view.unmount();
    expect(cart.teardown).toHaveBeenCalledTimes(1);
  });

  it("releases pointer capture on pause and never steps a reduced-motion game on the later pointer-up", () => {
    const cart = cartridge();
    const view = render(
      <ArcadeMount cartridge={cart} reducedMotion paused={false} />,
    );
    const canvas = screen.getByRole("application", { name: "Test cartridge" });
    let captured = false;
    const releasePointerCapture = vi.fn(() => {
      captured = false;
    });
    Object.assign(canvas, {
      setPointerCapture: vi.fn(() => {
        captured = true;
      }),
      hasPointerCapture: vi.fn(() => captured),
      releasePointerCapture,
    });

    fireEvent.pointerDown(canvas, { pointerId: 9, clientX: 10, clientY: 10 });
    expect(cart.update).toHaveBeenCalledTimes(1);
    view.rerender(<ArcadeMount cartridge={cart} reducedMotion paused />);
    expect(releasePointerCapture).toHaveBeenCalledWith(9);

    fireEvent.pointerUp(canvas, { pointerId: 9, clientX: 10, clientY: 10 });
    expect(cart.update).toHaveBeenCalledTimes(1);
    view.rerender(
      <ArcadeMount cartridge={cart} reducedMotion paused={false} />,
    );
    fireEvent.keyDown(canvas, { key: "Enter" });
    const resumedInput = (cart.update as ReturnType<typeof vi.fn>).mock
      .calls[1]?.[1];
    expect(resumedInput.pointerPressed).toBe(false);
    expect(resumedInput.pointerReleased).toBe(false);
  });

  it("keeps StrictMode setup and teardown balanced while an initially paused cartridge never updates", () => {
    const cart = cartridge();
    const view = render(
      <StrictMode>
        <ArcadeMount cartridge={cart} reducedMotion paused />
      </StrictMode>,
    );
    expect(cart.init).toHaveBeenCalledTimes(2);
    expect(cart.teardown).toHaveBeenCalledTimes(1);
    expect(cart.update).not.toHaveBeenCalled();
    view.unmount();
    expect(cart.teardown).toHaveBeenCalledTimes(2);
  });
});
