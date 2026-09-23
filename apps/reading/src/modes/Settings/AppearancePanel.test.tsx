/**
 * Settings > Appearance — choosing a theme or motion setting takes effect at
 * once (the <html> attributes the CSS and every reader key on), persists, and
 * the hint tells the truth about what is in force.
 */
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import AppearancePanel from "./AppearancePanel";

const html = document.documentElement;
const originalMatchMedia = window.matchMedia;

function choose(control: string, option: string) {
  const combo = screen.getByRole("combobox", { name: control });
  act(() => fireEvent.click(within(combo).getByRole("button")));
  act(() => fireEvent.click(within(combo).getByRole("option", { name: option })));
}

beforeEach(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (q: string) => ({
      matches: false,
      media: q,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  });
});
afterEach(() => {
  cleanup();
  window.localStorage.clear();
  for (const a of ["data-theme", "data-theme-pref", "data-motion"]) html.removeAttribute(a);
  Object.defineProperty(window, "matchMedia", { writable: true, configurable: true, value: originalMatchMedia });
});

describe("AppearancePanel", () => {
  it("offers System / Light / Dark and System / Reduce / Full, starting on System", () => {
    render(<AppearancePanel />);
    expect(screen.getByRole("combobox", { name: "Theme" }).textContent).toContain("System");
    expect(screen.getByRole("combobox", { name: "Motion" }).textContent).toContain("System");
    expect(screen.getByTestId("appearance-theme-hint").textContent).toBe("Follows your device. Light right now.");
  });

  it("choosing Dark switches the app now and remembers it", () => {
    render(<AppearancePanel />);
    choose("Theme", "Dark");
    expect(html.getAttribute("data-theme")).toBe("dark");
    expect(window.localStorage.getItem("antiek.theme")).toBe("dark");
    expect(screen.getByTestId("appearance-theme-hint").textContent).toContain("Dark in this browser");
  });

  it("choosing Reduce stills motion app-wide", () => {
    render(<AppearancePanel />);
    choose("Motion", "Reduce");
    expect(html.getAttribute("data-motion")).toBe("reduce");
    expect(screen.getByTestId("appearance-motion-hint").textContent).toBe(
      "Transitions are instant and the scene holds still.",
    );
  });
});
