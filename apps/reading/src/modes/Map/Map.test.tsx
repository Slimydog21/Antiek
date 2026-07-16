import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import Map, { DIRECTORY_DISTRICTS } from "./index";

afterEach(cleanup);

const EXPECTED_DIRECTORY_PATHS = [
  "/",
  "/deep-research",
  "/my-research",
  "/sources",
  "/documents",
  "/library",
  "/wrestle",
  "/readings",
  "/notebooks",
  "/brainstorm",
  "/write",
  "/speak",
  "/multimedia",
  "/outcomes",
  "/stats",
  "/settings",
  "/privacy",
  "/trust",
  "/billing",
  "/payouts",
  "/coordination",
  "/operator",
  "/home",
  "/create",
  "/biography",
  "/federation",
  "/cross-graph/citations",
  "/skill-rules",
  "/loop-3",
  "/pricing",
] as const;

const APP_SOURCE = readFileSync(resolve(process.cwd(), "src/App.tsx"), "utf8");

function renderMap() {
  return render(
    <MemoryRouter>
      <main>
        <Map />
      </main>
    </MemoryRouter>,
  );
}

describe("Igloo Directory", () => {
  it("composes under the shell's single main without adding a nested landmark", () => {
    const { container } = renderMap();
    expect(container.querySelectorAll("main")).toHaveLength(1);
    expect(container.querySelector(".igloo-directory")?.tagName).toBe("DIV");
    expect(
      screen.getByRole("heading", { level: 1, name: "The Igloo Directory" }),
    ).toBeTruthy();
    for (const district of DIRECTORY_DISTRICTS) {
      expect(screen.getByRole("region", { name: district.title })).toBeTruthy();
    }
    expect(screen.getByText(/curated wayfinding guide/i)).toBeTruthy();
  });

  it("matches the independently enumerated human-door contract and real router", () => {
    const { container } = renderMap();
    const hrefs = [...container.querySelectorAll("a")].map((link) =>
      link.getAttribute("href"),
    );
    expect(hrefs).toEqual(EXPECTED_DIRECTORY_PATHS);
    for (const path of EXPECTED_DIRECTORY_PATHS) {
      expect(APP_SOURCE).toContain(`<Route path="${path}"`);
    }
  });

  it("does not advertise redirect aliases or implementation-only routes", () => {
    const { container } = renderMap();
    const hrefs = [...container.querySelectorAll("a")].map((link) =>
      link.getAttribute("href"),
    );
    expect(hrefs).not.toContain("/investigations");
    expect(hrefs).not.toContain("/interviews");
    expect(hrefs).not.toContain("/_panel/:panelId");
    expect(hrefs.some((href) => href?.includes(":"))).toBe(false);
  });

  it("keeps the generated environment decorative and the reading language HTML-native", () => {
    const { container } = renderMap();
    const image = container.querySelector("img");
    expect(image?.getAttribute("alt")).toBe("");
    expect(image?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByText(/HTML edition/i)).toBeTruthy();
    expect(container.textContent).not.toMatch(/PDF/i);
    expect(container.textContent).not.toMatch(
      /every (operator-facing )?surface/i,
    );
  });
});
