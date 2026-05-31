import { describe, it, expect, beforeAll } from "vitest";
import { render } from "@testing-library/react";

import { KeyChip } from "./KeyChip";

// jsdom has no matchMedia; usePrefersReducedMotion needs it. (Matches the
// pattern in AdBorder.test.tsx / PenguinMascot.test.tsx.)
beforeAll(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }
});

describe("KeyChip — SPR-08", () => {
  it("renders an accessible (non-decorative) chip with aria-keyshortcuts", () => {
    const { container, unmount } = render(
      <KeyChip binding="mod+k" label="Command palette" />,
    );
    const chip = container.querySelector('[role="img"]') as HTMLElement;
    expect(chip).toBeTruthy();
    expect(chip.getAttribute("aria-keyshortcuts")).toBeTruthy();
    expect(chip.getAttribute("aria-label")).toMatch(/Command palette/);
    expect(chip.getAttribute("aria-label")).toMatch(/keyboard shortcut/i);
    unmount();
  });

  it("renders a single ⌘ combo as ONE glyph group with NO 'then' (the SPR-08 live shape)", () => {
    const { container, unmount } = render(
      <KeyChip binding="mod+e" label="Read" />,
    );
    expect(container.textContent).not.toContain("then");
    expect(container.querySelector(".antiek-keychip__then")).toBeNull();
    expect(container.querySelector(".antiek-keychip__seq")).toBeNull();
    // One kbd glyph element holding the composed glyph string (⌘E / CtrlE).
    const kbds = container.querySelectorAll(".antiek-keychip__key");
    expect(kbds.length).toBe(1);
    expect(kbds[0].textContent).toContain("E");
    unmount();
  });

  it("still renders a legacy/corrupt chord legibly (component behaviour unchanged; no live spec hits this)", () => {
    const { container, unmount } = render(
      <KeyChip binding="g r" label="Go to Research" />,
    );
    expect(container.textContent).toContain("then");
    const kbds = container.querySelectorAll(".antiek-keychip__key");
    expect(kbds.length).toBe(2);
    unmount();
  });

  it("can be marked decorative (hidden from a11y tree)", () => {
    const { container, unmount } = render(
      <KeyChip binding="mod+k" label="x" decorative />,
    );
    expect(container.querySelector('[role="img"]')).toBeNull();
    expect(container.querySelector('[aria-hidden="true"]')).toBeTruthy();
    unmount();
  });

  it("updates the rendered key when rebound", () => {
    const { container, rerender, unmount } = render(
      <KeyChip binding="j" label="Entity" />,
    );
    expect(container.textContent).toContain("J");
    rerender(<KeyChip binding="k" label="Entity" />);
    expect(container.textContent).toContain("K");
    expect(container.textContent).not.toContain("J");
    unmount();
  });
});
