/**
 * shellChrome.test.tsx — quiet chrome and the phone shell (design spec §4-§5,
 * audit-type-copy T5, the 2026-09-23 rendered critiques).
 *
 * Each block pins one rendered defect from the gallery:
 *  - the sun drawn as chrome (a 2.5px sun rule under the header, the section
 *    nav and on top of the dock; the Home key always filled sun);
 *  - the page title set as a lowercase mono slug ("library", "my-research");
 *  - an emoji (👤) as the account avatar;
 *  - the "Antiek is designed for ≥ 1024 px" banner instead of a phone layout,
 *    and a seven-key dock at 390 px that overlays the content;
 *  - the giant ghost brain (BrainPresence) behind every route, bleeding past
 *    the frame (77 px of sideways scroll at 1280);
 *  - the mascot parked over the working area (it covered inputs at 390).
 * The sun keeps exactly its three jobs: the dock's active key, the one
 * primary action, and the reading mark.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const { tierRef, authRef } = vi.hoisted(() => ({
  tierRef: { current: "xl" as string },
  authRef: {
    current: { status: "authenticated", identity: { user_id: "u", email: "reader@antiek.test", auth_method: "magic_link" } } as unknown,
  },
}));

vi.mock("../workspace/useViewportTier", () => ({ useViewportTier: () => tierRef.current }));
vi.mock("../lib/auth", async (orig) => ({
  ...(await orig<typeof import("../lib/auth")>()),
  useAuth: () => ({ state: authRef.current, refresh: async () => {}, signOut: async () => {} }),
}));

import { Topbar } from "../components/navigation/Topbar";
import { PanelLayout } from "../workspace/PanelLayout";
import { NavRail } from "./NavRail";
import { SceneChrome } from "./SceneChrome";

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

afterEach(() => {
  cleanup();
  tierRef.current = "xl";
});

const at = (path: string, ui: React.ReactNode) =>
  render(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>);

describe("the sun is not chrome", () => {
  it("the header and the section nav draw hairlines, not sun rules", () => {
    const { container } = at("/library", (
      <>
        <Topbar />
        <SceneChrome>
          <p>body</p>
        </SceneChrome>
      </>
    ));
    const header = container.querySelector("header")!;
    const scene = container.querySelector('[data-testid="scene-chrome-read"]')!;
    for (const el of [header, scene]) {
      expect(el.className).not.toMatch(/border-sun|border-b-edge/);
      expect(el.className).toMatch(/border-hairline/);
    }
    // The active tab is marked in ink, not sun.
    const active = within(scene as HTMLElement).getByRole("button", { name: "Library" });
    expect(active.className).not.toContain("border-sun");
  });

  it("the dock carries no sun edge, and Home is sun only when it is the active key", () => {
    const { container, unmount } = at("/library", <NavRail />);
    const dock = container.querySelector('[aria-label="Primary navigation"]')!;
    expect(dock.className).not.toContain("border-sun");
    const home = screen.getByRole("button", { name: "Antiek home" });
    expect(home.className).not.toMatch(/bg-sun|border-sun/);
    unmount();
    at("/home", <NavRail />);
    expect(screen.getByRole("button", { name: "Antiek home" }).className).toMatch(/bg-sun/);
  });
});

describe("the header names the page in words", () => {
  it("sets route words as sentence-case labels in the interface face", () => {
    at("/my-research", <Topbar />);
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(crumbs.textContent).toBe("My research");
    expect(crumbs.innerHTML).not.toContain("font-mono");
  });

  it("keeps a data id as data: verbatim, in the mono face", () => {
    at("/inv/7f3a9c21-44", <Topbar />);
    const id = screen.getByText("7f3a9c21-44");
    expect(id.className).toContain("font-mono");
    expect(screen.getByText("Investigation").className).not.toContain("font-mono");
  });

  it("draws the account as a lettermark, never an emoji", () => {
    at("/", <Topbar />);
    const account = screen.getByRole("button", { name: "Account" });
    expect(account.textContent).toBe("R");
    expect(account.textContent).not.toMatch(/\p{Extended_Pictographic}/u);
  });

  it("falls back to a drawn icon when there is no email", () => {
    authRef.current = { status: "authenticated", identity: { user_id: "u", email: null, auth_method: "local" } };
    at("/", <Topbar />);
    const account = screen.getByRole("button", { name: "Account" });
    expect(account.querySelector("svg")).toBeTruthy();
    expect(account.textContent).not.toMatch(/\p{Extended_Pictographic}/u);
  });
});

describe("the phone shell (390 px)", () => {
  it("shows no 'use a larger screen' banner, only the content", () => {
    tierRef.current = "sm";
    render(<PanelLayout mainSlot={<p>Main content</p>} />);
    expect(screen.getByText("Main content")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/designed for|larger\s+screen/i);
  });

  it("reduces the dock to five keys (four doors + More) that stay in the flow", () => {
    tierRef.current = "sm";
    const { container } = at("/library", <NavRail />);
    const dock = container.querySelector('[aria-label="Primary navigation"]') as HTMLElement;
    expect(dock).toBeTruthy();
    expect(dock.className).not.toMatch(/\babsolute\b/);
    const keys = within(dock).getAllByRole("button").map((b) => b.querySelector(".sr-only")?.textContent);
    expect(keys).toEqual(["Research", "Read", "Write", "Speak", "More"]);
    // No keyboard chips on a touch dock.
    expect(dock.querySelector("kbd, [aria-keyshortcuts]")).toBeNull();
    // A door press navigates; the dock does not collapse into a hamburger.
    within(dock).getAllByRole("button")[2].click();
    expect(screen.queryByRole("button", { name: "Open navigation" })).toBeNull();
  });

  it("reserves the mascot's station inside the dock, off the working area", () => {
    for (const tier of ["sm", "xl"]) {
      tierRef.current = tier;
      const { container, unmount } = at("/library", <NavRail />);
      const dock = container.querySelector('[aria-label="Primary navigation"]')!;
      const station = container.querySelector("[data-mascot-station]");
      expect(station, tier).toBeTruthy();
      expect(dock.contains(station)).toBe(true);
      expect(station!.getAttribute("aria-hidden")).toBe("true");
      unmount();
    }
  });
});

describe("mono is for data, never for a button label (spec §3, T5)", () => {
  it("LemonButton sets its label in the interface face at weight 500", async () => {
    const { default: LemonButton } = await import("../components/lemon/LemonButton");
    render(<LemonButton variant="primary">Start a research</LemonButton>);
    const cls = screen.getByRole("button", { name: "Start a research" }).className;
    expect(cls).not.toContain("font-mono");
    expect(cls).toContain("font-sans");
    expect(cls).toContain("font-medium");
  });
});

describe("one lit key", () => {
  it("on /home only the Home key is active, not the Research door it belongs to", () => {
    const { container } = at("/home", <NavRail />);
    const lit = [...container.querySelectorAll('[aria-label="Primary navigation"] button')].filter((b) =>
      /\bbg-sun\b/.test(b.className),
    );
    expect(lit.map((b) => b.getAttribute("aria-label") ?? b.querySelector(".sr-only")?.textContent)).toEqual([
      "Antiek home",
    ]);
  });
});

describe("empty docks draw nothing", () => {
  it("a dock with no panels has no edge line at the working region's side", () => {
    tierRef.current = "xl";
    const { container } = render(<PanelLayout mainSlot={<p>Main content</p>} />);
    for (const label of ["Left dock", "Right dock"]) {
      const dock = container.querySelector(`[aria-label="${label}"]`)!;
      expect(dock.className, label).not.toMatch(/border-(l|r)\b|border-sun/);
    }
  });
});
