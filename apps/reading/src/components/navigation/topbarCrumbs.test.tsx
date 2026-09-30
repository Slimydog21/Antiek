/**
 * topbarCrumbs.test.tsx — lane A stage B3, defect 9.
 *
 * The Topbar named a record by its URL slug ("Investigation › Inv finches").
 * A record crumb (/inv/:id, /read/:id, /write/:id) is named the way its tab
 * is: the title from tabTitles through labelForTab, never the slug and never
 * a raw id; while the title is unknown it reads as the kind's noun.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../lib/auth", async (orig) => ({
  ...(await orig<typeof import("../../lib/auth")>()),
  useAuth: () => ({
    state: { status: "authenticated", identity: { user_id: "u", email: "reader@antiek.test", auth_method: "magic_link" } },
    refresh: async () => {},
    signOut: async () => {},
  }),
}));

import { Topbar } from "./Topbar";
import { resetTabTitles, setTabTitle, setTitleResolvers } from "../../workspace/tabTitles";

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

beforeEach(() => {
  resetTabTitles();
  // No network in this test: every lookup is the test's to answer.
  setTitleResolvers({});
});

afterEach(() => {
  cleanup();
  resetTabTitles();
});

const at = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Topbar />
    </MemoryRouter>,
  );
const crumbs = () => screen.getByRole("navigation", { name: "Breadcrumb" });

describe("B3-9 record crumbs are named like their tabs", () => {
  it("an investigation is named by its question, never its slug", async () => {
    setTabTitle("research", "/inv/inv-finches", "Did beak depth track the 1977 drought?");
    at("/inv/inv-finches");
    expect(await screen.findByText("Did beak depth track the 1977 drought?")).toBeTruthy();
    expect(crumbs().textContent).not.toMatch(/Inv finches/);
    expect(crumbs().textContent).toMatch(/^Investigation›/);
  });

  it("a book by its title, a piece by its title", async () => {
    setTabTitle("reader", "origin-of-species", "On the Origin of Species");
    at("/read/origin-of-species");
    expect(await screen.findByText("On the Origin of Species")).toBeTruthy();
    expect(crumbs().textContent).not.toMatch(/Origin of species$/);
    cleanup();
    setTabTitle("document", "/write/del-finches", "Why the finches matter");
    at("/write/del-finches");
    expect(await screen.findByText("Why the finches matter")).toBeTruthy();
    expect(crumbs().textContent).not.toMatch(/Del finches/);
  });

  it("an unknown title is looked up; until it lands the crumb reads as the kind, never the slug", async () => {
    let answer: (t: string) => void = () => {};
    setTitleResolvers({ research: () => new Promise<string>((r) => (answer = r)) });
    at("/inv/inv-finches");
    const text = await screen.findByText("Research");
    expect(text).toBeTruthy();
    expect(crumbs().textContent).not.toMatch(/Inv finches|inv-finches/);
    await act(async () => {
      answer("Did beak depth track the 1977 drought?");
    });
    expect(await screen.findByText("Did beak depth track the 1977 drought?")).toBeTruthy();
  });

  it("a raw id is never a label: a failed lookup falls to the noun", async () => {
    setTitleResolvers({ research: () => Promise.reject(new Error("offline")) });
    at("/inv/7f3a9c21-44");
    expect(await screen.findByText("Research")).toBeTruthy();
    expect(crumbs().textContent).not.toContain("7f3a9c21-44");
  });

  it("route words keep their sentence-case labels", () => {
    at("/my-research");
    expect(crumbs().textContent).toBe("My research");
  });
});
