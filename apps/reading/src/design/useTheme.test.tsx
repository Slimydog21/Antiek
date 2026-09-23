/**
 * useTheme / useMotionPreference / usePrefersReducedMotion — the one reactive
 * appearance source. Behaviour, not implementation: each test drives a real
 * input (the OS setting via matchMedia, the in-app setter, another tab's
 * storage event, blocked storage) and reads what a component would see.
 */
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";
import { MOTION_KEY, THEME_KEY } from "./theme";
import { useMotionPreference, useTheme } from "./useTheme";

const os = { dark: false, reduce: false };
const listeners = new Set<() => void>();
const originalMatchMedia = window.matchMedia;

function installMatchMedia() {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      get matches() {
        if (query.includes("prefers-color-scheme: dark")) return os.dark;
        if (query.includes("prefers-reduced-motion: reduce")) return os.reduce;
        return false;
      },
      media: query,
      onchange: null,
      addEventListener: (_: string, cb: () => void) => listeners.add(cb),
      removeEventListener: (_: string, cb: () => void) => listeners.delete(cb),
      addListener: (cb: () => void) => listeners.add(cb),
      removeListener: (cb: () => void) => listeners.delete(cb),
      dispatchEvent: () => false,
    }),
  });
}

/** Flip an OS setting and fire the change listeners, as the browser does. */
function osChange(patch: Partial<typeof os>) {
  act(() => {
    Object.assign(os, patch);
    for (const cb of [...listeners]) cb();
  });
}

function reset() {
  const html = document.documentElement;
  for (const a of ["data-theme", "data-theme-pref", "data-motion"]) html.removeAttribute(a);
  window.localStorage.clear();
  os.dark = false;
  os.reduce = false;
  listeners.clear();
}

function Probe() {
  const theme = useTheme();
  const motion = useMotionPreference();
  const reduced = usePrefersReducedMotion();
  return (
    <div>
      <span data-testid="theme">{`${theme.preference}/${theme.resolved}`}</span>
      <span data-testid="motion">{`${motion.preference}/${motion.reduced}`}</span>
      <span data-testid="reduced">{String(reduced)}</span>
      <button onClick={() => theme.setPreference("dark")}>dark</button>
      <button onClick={() => theme.setPreference("light")}>light</button>
      <button onClick={() => theme.setPreference("system")}>system</button>
      <button onClick={() => motion.setPreference("reduce")}>reduce</button>
      <button onClick={() => motion.setPreference("full")}>full</button>
      <button onClick={() => motion.setPreference("system")}>motion-system</button>
    </div>
  );
}

const text = (id: string) => screen.getByTestId(id).textContent;
const click = (name: string) => act(() => screen.getByText(name).click());

beforeEach(() => {
  reset();
  installMatchMedia();
});
afterEach(() => {
  cleanup();
  reset();
  Object.defineProperty(window, "matchMedia", { writable: true, configurable: true, value: originalMatchMedia });
  vi.restoreAllMocks();
});

describe("useTheme", () => {
  it("defaults to system and follows the OS, live, without a reload", () => {
    render(<Probe />);
    expect(text("theme")).toBe("system/light");
    osChange({ dark: true });
    expect(text("theme")).toBe("system/dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    osChange({ dark: false });
    expect(text("theme")).toBe("system/light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("an explicit choice wins over the OS, persists, and System hands control back", () => {
    render(<Probe />);
    click("dark");
    expect(text("theme")).toBe("dark/dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(window.localStorage.getItem(THEME_KEY)).toBe("dark");
    osChange({ dark: false }); // the OS says light; the user said dark
    expect(text("theme")).toBe("dark/dark");
    click("system");
    expect(text("theme")).toBe("system/light");
    expect(window.localStorage.getItem(THEME_KEY)).toBeNull();
  });

  it("follows a change made in another tab (storage event)", () => {
    render(<Probe />);
    act(() => {
      window.localStorage.setItem(THEME_KEY, "dark");
      window.dispatchEvent(new StorageEvent("storage", { key: THEME_KEY, newValue: "dark" }));
    });
    expect(text("theme")).toBe("dark/dark");
  });

  it("keeps working when storage is blocked (private window): session-only preference", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    render(<Probe />);
    expect(text("theme")).toBe("system/light");
    click("dark");
    expect(text("theme")).toBe("dark/dark");
  });

  it("syncs the browser-chrome colour (meta theme-color) to the page ground", () => {
    const meta = document.createElement("meta");
    meta.name = "theme-color";
    document.head.appendChild(meta);
    document.documentElement.style.setProperty("--bg-page", "rgb(18, 52, 86)");
    try {
      render(<Probe />);
      click("dark");
      expect(meta.getAttribute("content")).toBe("rgb(18, 52, 86)");
    } finally {
      meta.remove();
      document.documentElement.style.removeProperty("--bg-page");
    }
  });
});

describe("motion preference", () => {
  it("System follows the OS reduce-motion setting, live", () => {
    render(<Probe />);
    expect(text("reduced")).toBe("false");
    osChange({ reduce: true });
    expect(text("reduced")).toBe("true");
    expect(text("motion")).toBe("system/true");
  });

  it("Reduce wins over an OS that allows motion, and marks <html> for the CSS catch-all", () => {
    render(<Probe />);
    click("reduce");
    expect(text("reduced")).toBe("true");
    expect(document.documentElement.getAttribute("data-motion")).toBe("reduce");
    expect(window.localStorage.getItem(MOTION_KEY)).toBe("reduce");
  });

  it("Full keeps motion on even when the OS asks to reduce", () => {
    os.reduce = true;
    render(<Probe />);
    expect(text("reduced")).toBe("true");
    click("full");
    expect(text("reduced")).toBe("false");
    expect(document.documentElement.getAttribute("data-motion")).toBe("full");
    click("motion-system");
    expect(text("reduced")).toBe("true");
    expect(document.documentElement.hasAttribute("data-motion")).toBe(false);
  });

  it("usePrefersReducedMotion is false without matchMedia (jsdom default, SSR-like)", () => {
    Object.defineProperty(window, "matchMedia", { writable: true, configurable: true, value: undefined });
    render(<Probe />);
    expect(text("reduced")).toBe("false");
    expect(text("theme")).toBe("system/light");
  });
});
