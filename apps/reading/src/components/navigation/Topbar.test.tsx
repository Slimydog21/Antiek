import { afterEach, describe, it, expect } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { Topbar } from "./Topbar";
import { SCENE_REGISTRY } from "../../shell/sceneRegistry";

afterEach(() => cleanup());

/**
 * SPR-05 — the Topbar IS the scene chrome on workflow routes and bare on
 * shared routes. These tests pin that switch: the chrome (action bar + tab
 * strip) appears for a workflow route and is absent for a shared one, while
 * search + account survive in both.
 */

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Topbar />
    </MemoryRouter>,
  );
}

describe("Topbar — scene chrome on workflow routes", () => {
  it("renders the active workflow's actions + tab strip on a workflow route", () => {
    renderAt("/"); // research home
    // Action bar: the research verbs are present as buttons.
    for (const a of SCENE_REGISTRY.research.actions) {
      expect(screen.getByRole("button", { name: a.label })).toBeTruthy();
    }
    // Tab strip: the scene-views nav exists, with the built Synthesis tab.
    expect(screen.getByRole("navigation", { name: "Scene views" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Synthesis" })).toBeTruthy();
  });

  it("renders a soon tab as a disabled affordance, not a link", () => {
    renderAt("/documents"); // read workflow — has a `soon` Rabbit-hole tab
    const soon = SCENE_REGISTRY.read.tabs.find((t) => t.builtState === "soon")!;
    // The soon tab text renders but is not a link.
    expect(screen.getByText(soon.label)).toBeTruthy();
    expect(screen.queryByRole("link", { name: soon.label })).toBeNull();
    // The "soon" badge is present.
    expect(screen.getAllByText("soon").length).toBeGreaterThan(0);
  });
});

describe("Topbar — bare on shared/operator routes", () => {
  it("renders no action bar + no tab strip on a shared route", () => {
    renderAt("/billing");
    // No scene-views nav.
    expect(screen.queryByRole("navigation", { name: "Scene views" })).toBeNull();
    // None of the research verbs leak onto a shared route.
    for (const a of SCENE_REGISTRY.research.actions) {
      expect(screen.queryByRole("button", { name: a.label })).toBeNull();
    }
  });

  it("keeps search + account intact on both route kinds", () => {
    const onShared = renderAt("/settings");
    expect(onShared.getByRole("button", { name: "Account" })).toBeTruthy();
    expect(onShared.getByPlaceholderText("search · ⌘K")).toBeTruthy();
    cleanup();

    const onWorkflow = renderAt("/");
    expect(onWorkflow.getByRole("button", { name: "Account" })).toBeTruthy();
    expect(onWorkflow.getByPlaceholderText("search · ⌘K")).toBeTruthy();
  });
});
