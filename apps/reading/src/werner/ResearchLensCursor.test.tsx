import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ResearchLensCursor } from "./ResearchLensCursor";

let clock = 0;

beforeEach(() => {
  clock = 0;
  vi.useFakeTimers();
  Object.defineProperty(document, "hidden", {
    value: false,
    configurable: true,
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("ResearchLensCursor", () => {
  it("renders HTML-native lens chrome without capturing input", () => {
    const { getByTestId } = render(<ResearchLensCursor now={() => clock} />);
    const lens = getByTestId("research-lens-cursor");
    expect(lens.getAttribute("aria-hidden")).toBe("true");
    expect(lens.querySelector(".research-lens-cursor__glass")).toBeTruthy();
  });

  it("tracks the live pointer and marks the idle state", () => {
    const { getByTestId } = render(<ResearchLensCursor now={() => clock} />);
    const lens = getByTestId("research-lens-cursor") as HTMLSpanElement;

    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 420, clientY: 240 }),
      );
      vi.advanceTimersByTime(32);
    });
    expect(lens.style.left).toBe("420px");
    expect(lens.style.top).toBe("240px");
    expect(lens.style.display).toBe("block");
    expect(lens.classList.contains("research-lens-cursor--idle")).toBe(false);

    clock = 2400;
    act(() => vi.advanceTimersByTime(32));
    expect(lens.classList.contains("research-lens-cursor--idle")).toBe(true);
  });

  it("renders nothing when disabled so reduced-motion keeps the native cursor", () => {
    const { queryByTestId } = render(<ResearchLensCursor disabled />);
    expect(queryByTestId("research-lens-cursor")).toBeNull();
  });
});
