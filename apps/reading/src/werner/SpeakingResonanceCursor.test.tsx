import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SpeakingResonanceCursor } from "./SpeakingResonanceCursor";

let clock = 0;
const resonanceCss = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "speaking-resonance.css"),
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
  document.documentElement.classList.remove("werner-speaking-resonance-active");
  vi.useRealTimers();
});

describe("SpeakingResonanceCursor", () => {
  it("renders inert listening chrome", () => {
    const { getByTestId } = render(
      <SpeakingResonanceCursor now={() => clock} />,
    );
    const microphone = getByTestId("speaking-resonance-cursor");
    expect(microphone.getAttribute("aria-hidden")).toBe("true");
    expect(
      microphone.querySelector(".speaking-resonance-cursor__grille"),
    ).toBeTruthy();
    expect(resonanceCss).toMatch(
      /\.speaking-resonance-cursor\s*\{[^}]*pointer-events:\s*none/s,
    );
  });

  it("tracks the live pointer and settles when idle", () => {
    const { getByTestId } = render(
      <SpeakingResonanceCursor now={() => clock} />,
    );
    const microphone = getByTestId(
      "speaking-resonance-cursor",
    ) as HTMLSpanElement;

    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 280, clientY: 164 }),
      );
      vi.advanceTimersByTime(32);
    });
    expect(microphone.style.left).toBe("280px");
    expect(microphone.style.top).toBe("164px");
    expect(microphone.style.display).toBe("block");
    expect(
      microphone.classList.contains("speaking-resonance-cursor--idle"),
    ).toBe(false);

    clock = 2400;
    act(() => vi.advanceTimersByTime(32));
    expect(
      microphone.classList.contains("speaking-resonance-cursor--idle"),
    ).toBe(true);
  });

  it("hides while the tab is hidden", () => {
    const { getByTestId } = render(
      <SpeakingResonanceCursor now={() => clock} />,
    );
    const microphone = getByTestId(
      "speaking-resonance-cursor",
    ) as HTMLSpanElement;
    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 72, clientY: 88 }),
      );
      vi.advanceTimersByTime(32);
    });
    expect(microphone.style.display).toBe("block");

    Object.defineProperty(document, "hidden", {
      value: true,
      configurable: true,
    });
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
      vi.advanceTimersByTime(32);
    });
    expect(microphone.style.display).toBe("none");
  });

  it("scopes duplicate-cursor suppression to the mounted activity", () => {
    expect(resonanceCss).toMatch(
      /html\.werner-speaking-resonance-active\.werner-ice-cursor-hidden \*\s*\{[^}]*cursor:\s*none\s*!important/s,
    );
    const { unmount } = render(<SpeakingResonanceCursor now={() => clock} />);
    expect(document.documentElement.classList).toContain(
      "werner-speaking-resonance-active",
    );
    unmount();
    expect(document.documentElement.classList).not.toContain(
      "werner-speaking-resonance-active",
    );
  });

  it("renders nothing when disabled so reduced motion keeps the native cursor", () => {
    const { queryByTestId } = render(<SpeakingResonanceCursor disabled />);
    expect(queryByTestId("speaking-resonance-cursor")).toBeNull();
    expect(document.documentElement.classList).not.toContain(
      "werner-speaking-resonance-active",
    );
  });
});
