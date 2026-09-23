/**
 * PanelLayout.motion.test.tsx — opening a dock snaps its width and fades its
 * contents (design audit 2026-09-23, M5).
 *
 * The side docks used to animate `width` over 150ms, which reflowed the
 * reading column on every frame and left MasterMdViewer's measured widgets
 * stale until its ResizeObserver caught up. Now the width commits in one
 * layout and the contents arrive by opacity alone. The "no width transition"
 * half is enforced repo-wide by src/design/motion/layoutMotion.guard.test.ts;
 * the frame-by-frame width trace is measured in a real browser (see the PR).
 *
 * PanelLayoutPanel pulls the whole panel registry (a PDF worker jsdom cannot
 * load), so it is replaced by a stub that renders the panel id.
 */
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PanelLayout } from "./PanelLayout";
import { useWorkspace } from "./WorkspaceStore";

vi.mock("./PanelLayoutPanel", () => ({
  PanelLayoutPanel: ({ id }: { id: string }) => <div data-testid={`panel-${id}`} />,
}));
vi.mock("../components/lemon/LemonToast", () => ({ toast: { info: () => {} } }));

function stubMatchMedia(reduce: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: reduce && query.includes("prefers-reduced-motion"),
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

function installRaf() {
  const pending: FrameRequestCallback[] = [];
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => pending.push(cb));
  vi.stubGlobal("cancelAnimationFrame", () => {});
  return () =>
    act(() => {
      for (const cb of pending.splice(0)) cb(16);
    });
}

const leftDock = (root: HTMLElement) =>
  root.querySelector('aside[aria-label="Left dock"]') as HTMLElement;

beforeEach(() => {
  useWorkspace.getState().reset();
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 1440 });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PanelLayout — docks snap, contents fade", () => {
  it("opening a dock commits the full width at once and fades the contents in by opacity", () => {
    stubMatchMedia(false);
    const nextFrame = installRaf();
    const { container } = render(<PanelLayout mainSlot={<p>main</p>} />);
    expect(leftDock(container).style.width).toBe("0px");

    act(() => {
      useWorkspace.getState().open("FakeSidebar", {}, { mode: "docked-left", id: "t:left" });
    });
    const dock = leftDock(container);
    // Snap: the committed width is final in the same render, no width easing.
    expect(dock.style.width).toBe("320px");
    expect(dock.className).not.toMatch(/transition/);
    // The contents arrive faded, then flip on the next frame.
    const fade = dock.querySelector("[data-enter]") as HTMLElement;
    expect(fade).not.toBeNull();
    expect(fade.getAttribute("data-enter")).toBe("false");
    expect(fade.className).toContain("transition-opacity");
    expect(fade.className).toContain("data-[enter=false]:opacity-0");
    expect(fade.querySelector('[data-testid="panel-t:left"]')).not.toBeNull();
    nextFrame();
    expect(fade.getAttribute("data-enter")).toBe("true");
  });

  it("under reduced motion the contents mount fully visible (no fade)", () => {
    stubMatchMedia(true);
    installRaf();
    const { container } = render(<PanelLayout mainSlot={<p>main</p>} />);
    act(() => {
      useWorkspace.getState().open("FakeSidebar", {}, { mode: "docked-left", id: "t:left" });
    });
    const fade = leftDock(container).querySelector("[data-enter]") as HTMLElement;
    expect(fade.getAttribute("data-enter")).toBe("true");
  });
});
