import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter, useLocation, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { DocumentTabStrip } from "./DocumentTabStrip";
import { pinPlatform, press, unpinPlatform } from "./keymapTestKit";
import { useWorkspaceShortcuts } from "./shortcuts";
import { useTabTrees } from "./tabTreeStore";

function Workspace() {
  const location = useLocation();
  useWorkspaceShortcuts(useNavigate());
  return (
    <>
      <output data-testid="route">{location.pathname}</output>
      <DocumentTabStrip />
    </>
  );
}

beforeEach(() => {
  pinPlatform("mac");
  useTabTrees.getState().resetTabTrees();
  vi.stubGlobal("fetch", async () => Response.json({}, { status: 404 }));
});
afterEach(() => {
  cleanup();
  useTabTrees.getState().resetTabTrees();
  unpinPlatform();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
});

it.each([
  ["previous then next", "beta", "alpha", "ctrl+alt+[", "ctrl+alt+]"],
  ["next then previous", "alpha", "beta", "ctrl+alt+]", "ctrl+alt+["],
])("keeps %s when the second key follows history before React renders", async (_label, start, middle, first, second) => {
  const tabs = useTabTrees.getState();
  await tabs.ensureMothership("reading");
  for (const name of ["alpha", "beta"]) {
    tabs.spawnTab("reading", null, {
      tab_id: name, kind: "reader", ref: name, mothership: "reading", activate: false,
    });
  }
  window.history.replaceState({}, "", `/read/${start}`);
  render(<BrowserRouter><Workspace /></BrowserRouter>);
  await waitFor(() => expect(useTabTrees.getState().trees.reading?.active_tab_id).toBe(start));

  const push = window.history.pushState.bind(window.history);
  let injected = false;
  vi.spyOn(window.history, "pushState").mockImplementation((state, unused, url) => {
    push(state, unused, url);
    if (String(url) === `/read/${middle}` && !injected) {
      injected = true;
      // The browser URL has changed; BrowserRouter has not rendered it yet.
      press(window, second, "mac");
    }
  });
  await act(async () => {
    press(window, first, "mac");
  });
  expect(injected).toBe(true);
  await waitFor(() => {
    expect(window.location.pathname).toBe(`/read/${start}`);
    expect(screen.getByTestId("route").textContent).toBe(`/read/${start}`);
    expect(useTabTrees.getState().trees.reading?.active_tab_id).toBe(start);
    expect(document.querySelector('[data-tab-id][aria-selected="true"]')?.getAttribute("data-tab-id")).toBe(start);
  });
});

it("does not let an old tab intent override a newer ordinary route", async () => {
  const tabs = useTabTrees.getState();
  await tabs.ensureMothership("reading");
  for (const name of ["alpha", "beta"]) {
    tabs.spawnTab("reading", null, {
      tab_id: name, kind: "reader", ref: name, mothership: "reading", activate: false,
    });
  }
  window.history.replaceState({}, "", "/read/alpha");
  render(<BrowserRouter><Workspace /></BrowserRouter>);
  await waitFor(() => expect(useTabTrees.getState().trees.reading?.active_tab_id).toBe("alpha"));
  await act(async () => {
    press(window, "ctrl+alt+]", "mac");
    window.history.pushState({}, "", "/library");
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
  expect(window.location.pathname).toBe("/library");
  expect(screen.getByTestId("route").textContent).toBe("/library");
  expect(useTabTrees.getState().navIntent).toBeNull();
});
