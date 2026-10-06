import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import { SceneChrome } from "./SceneChrome";
import { WORKFLOWS } from "./workflowTaxonomy";

afterEach(cleanup);

function RouteProbe() {
  const { pathname } = useLocation();
  return <output aria-label="Current route">{pathname}</output>;
}

function mount(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <SceneChrome>
        <RouteProbe />
      </SceneChrome>
    </MemoryRouter>,
  );
  return within(screen.getByRole("navigation", { name: "Read views" }));
}

// Router UNIT controls. No book body, authentication or provider fixture.
describe("Library return in the Read scene", () => {
  it("returns from the observed reader route to Library and keeps its child mounted", () => {
    const views = mount("/read/doc-book-ef687fdce87b52ae");
    const child = screen.getByLabelText("Current route");

    fireEvent.click(views.getByRole("button", { name: "Library" }));

    expect(child.textContent).toBe("/library");
    expect(child.textContent).toBe(WORKFLOWS.read.defaultRoute);
    expect(screen.getByLabelText("Current route")).toBe(child);
    expect(views.getByRole("button", { name: "Library" }).getAttribute("aria-current")).toBe("page");
  });

  it.each(["/library", "/library/browse"])("marks Library as current on %s", (path) => {
    const views = mount(path);
    expect(views.getByRole("button", { name: "Library" }).getAttribute("aria-current")).toBe("page");
  });

  it.each([
    { label: "Documents", path: "/documents" },
    { label: "Notebooks", path: "/notebooks" },
  ])("preserves the $label destination", ({ label, path }) => {
    const views = mount("/read/doc-book-ef687fdce87b52ae");
    fireEvent.click(views.getByRole("button", { name: label }));
    expect(screen.getByLabelText("Current route").textContent).toBe(path);
    if (path === "/documents") {
      expect(screen.queryByRole("navigation", { name: "Read views" })).toBeNull();
    } else {
      expect(views.getByRole("button", { name: label }).getAttribute("aria-current")).toBe("page");
    }
  });
});
