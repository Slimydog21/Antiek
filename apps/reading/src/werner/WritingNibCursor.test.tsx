import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WritingNibCursor } from "./WritingNibCursor";

let clock = 0;
const nibCss = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "writing-nib.css"),
  "utf8",
);

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
  document.documentElement.classList.remove("werner-ice-cursor-hidden");
  document.documentElement.classList.remove("werner-writing-nib-active");
  vi.useRealTimers();
});

describe("WritingNibCursor", () => {
  it("renders semantic-free nib chrome without capturing input", () => {
    const { getByTestId } = render(<WritingNibCursor now={() => clock} />);
    const nib = getByTestId("writing-nib-cursor");
    expect(nib.getAttribute("aria-hidden")).toBe("true");
    expect(nib.querySelector(".writing-nib-cursor__breather")).toBeTruthy();
    expect(nib.querySelector(".writing-nib-cursor__slit")).toBeTruthy();
    expect(nibCss).toMatch(
      /\.writing-nib-cursor\s*\{[^}]*pointer-events:\s*none/s,
    );
  });

  it("suppresses explicit descendant cursors while the instrument is active", () => {
    expect(nibCss).toMatch(
      /html\.werner-writing-nib-active\.werner-ice-cursor-hidden \*\s*\{[^}]*cursor:\s*none\s*!important/s,
    );
    expect(nibCss).toMatch(
      /html\.werner-writing-nib-active\.werner-ice-cursor-hidden\s+button\[data-testid="penguin-mascot"\][\s\S]*?cursor:\s*none\s*!important/,
    );
  });

  it("scopes descendant suppression to the mounted writing activity", () => {
    const { unmount } = render(<WritingNibCursor now={() => clock} />);
    expect(document.documentElement.classList).toContain(
      "werner-writing-nib-active",
    );

    unmount();
    expect(document.documentElement.classList).not.toContain(
      "werner-writing-nib-active",
    );
  });

  it("tracks the live pointer and settles when the pointer is idle", () => {
    const { getByTestId } = render(<WritingNibCursor now={() => clock} />);
    const nib = getByTestId("writing-nib-cursor") as HTMLSpanElement;

    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 360, clientY: 212 }),
      );
      vi.advanceTimersByTime(32);
    });
    expect(nib.style.left).toBe("360px");
    expect(nib.style.top).toBe("212px");
    expect(nib.style.display).toBe("block");
    expect(nib.classList.contains("writing-nib-cursor--idle")).toBe(false);

    clock = 2400;
    act(() => vi.advanceTimersByTime(32));
    expect(nib.classList.contains("writing-nib-cursor--idle")).toBe(true);
  });

  it("hides while the tab is hidden", () => {
    const { getByTestId } = render(<WritingNibCursor now={() => clock} />);
    const nib = getByTestId("writing-nib-cursor") as HTMLSpanElement;

    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 80, clientY: 90 }),
      );
      vi.advanceTimersByTime(32);
    });
    expect(nib.style.display).toBe("block");

    Object.defineProperty(document, "hidden", {
      value: true,
      configurable: true,
    });
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
      vi.advanceTimersByTime(32);
    });
    expect(nib.style.display).toBe("none");
  });

  it("renders nothing when disabled so reduced motion keeps the native cursor", () => {
    const { queryByTestId } = render(<WritingNibCursor disabled />);
    expect(queryByTestId("writing-nib-cursor")).toBeNull();
  });
});
