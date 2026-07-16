import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BrassBalanceCursor } from "./BrassBalanceCursor";

let clock = 0;
const balanceCss = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "brass-balance.css"),
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
  document.documentElement.classList.remove("werner-brass-balance-active");
  document.documentElement.classList.remove("werner-brass-balance-ready");
  vi.useRealTimers();
});

describe("BrassBalanceCursor", () => {
  it("renders semantic-free scale chrome without capturing input", () => {
    const { getByTestId } = render(<BrassBalanceCursor now={() => clock} />);
    const el = getByTestId("brass-balance-cursor");
    expect(el.getAttribute("aria-hidden")).toBe("true");
    expect(el.querySelector(".brass-balance-cursor__beam")).toBeTruthy();
    expect(el.querySelector(".brass-balance-cursor__pivot")).toBeTruthy();
    expect(el.querySelector(".brass-balance-cursor__post")).toBeTruthy();
    expect(el.querySelector(".brass-balance-cursor__pan--left")).toBeTruthy();
    expect(el.querySelector(".brass-balance-cursor__pan--right")).toBeTruthy();
    expect(balanceCss).toMatch(
      /\.brass-balance-cursor\s*\{[^}]*pointer-events:\s*none/s,
    );
  });

  it("suppresses explicit descendant cursors while the instrument is active", () => {
    expect(balanceCss).toMatch(
      /html\.werner-brass-balance-active\.werner-brass-balance-ready\.werner-ice-cursor-hidden[\s\S]*?\*\s*\{[^}]*cursor:\s*none\s*!important/,
    );
    expect(balanceCss).toMatch(
      /html\.werner-brass-balance-active\.werner-brass-balance-ready\.werner-ice-cursor-hidden\s+button\[data-testid="penguin-mascot"\][\s\S]*?cursor:\s*none\s*!important/,
    );
  });

  it("keeps the native cursor until a replacement coordinate exists", () => {
    render(<BrassBalanceCursor now={() => clock} />);
    expect(document.documentElement.classList).toContain(
      "werner-brass-balance-active",
    );
    expect(document.documentElement.classList).not.toContain(
      "werner-brass-balance-ready",
    );
    expect(balanceCss).toMatch(
      /html\.werner-brass-balance-active:not\(\.werner-brass-balance-ready\)\s*\{[^}]*cursor:\s*auto\s*!important/s,
    );
  });

  it("scopes descendant suppression to the mounted brass-balance activity", () => {
    const { unmount } = render(<BrassBalanceCursor now={() => clock} />);
    expect(document.documentElement.classList).toContain(
      "werner-brass-balance-active",
    );

    unmount();
    expect(document.documentElement.classList).not.toContain(
      "werner-brass-balance-active",
    );
  });

  it("tracks the live pointer and settles when the pointer is idle", () => {
    const { getByTestId } = render(<BrassBalanceCursor now={() => clock} />);
    const el = getByTestId("brass-balance-cursor") as HTMLSpanElement;

    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 360, clientY: 212 }),
      );
      vi.advanceTimersByTime(32);
    });
    expect(el.style.left).toBe("360px");
    expect(el.style.top).toBe("212px");
    expect(el.style.display).toBe("block");
    expect(document.documentElement.classList).toContain(
      "werner-brass-balance-ready",
    );
    expect(el.classList.contains("brass-balance-cursor--idle")).toBe(false);
    expect(el.classList.contains("brass-balance-cursor--active")).toBe(true);

    clock = 2400;
    act(() => vi.advanceTimersByTime(32));
    expect(el.classList.contains("brass-balance-cursor--idle")).toBe(true);
    expect(el.classList.contains("brass-balance-cursor--active")).toBe(false);
  });

  it("hides while the tab is hidden", () => {
    const { getByTestId } = render(<BrassBalanceCursor now={() => clock} />);
    const el = getByTestId("brass-balance-cursor") as HTMLSpanElement;

    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 80, clientY: 90 }),
      );
      vi.advanceTimersByTime(32);
    });
    expect(el.style.display).toBe("block");

    Object.defineProperty(document, "hidden", {
      value: true,
      configurable: true,
    });
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
      vi.advanceTimersByTime(32);
    });
    expect(el.style.display).toBe("none");
  });

  it("renders nothing when disabled so reduced motion keeps the native cursor", () => {
    const { queryByTestId } = render(<BrassBalanceCursor disabled />);
    expect(queryByTestId("brass-balance-cursor")).toBeNull();
  });
});
