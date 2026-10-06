import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter, Link, useLocation, useNavigate } from "react-router-dom";

import { prefixState } from "../components/hotkeys/prefixState";
import { DocumentTabStrip } from "./DocumentTabStrip";
import { ProjectPicker } from "./ProjectPicker";
import { pinPlatform, press, unpinPlatform } from "./keymapTestKit";
import { clearTabProject } from "./persistence";
import { installShortcuts } from "./shortcuts";
import { createInMemoryTabTreeAdapter } from "./tabTree";
import { TAB_PROJECT_ID, useTabTrees } from "./tabTreeStore";

const tabs = () => useTabTrees.getState();

function RouteAndKeys() {
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => installShortcuts(navigate), [navigate]);
  return (
    <>
      <output data-testid="route">{location.pathname}</output>
      <Link to="/read/doc-two">Second document</Link>
      <Link to="/read/doc-three">Third document</Link>
      <DocumentTabStrip />
      <ProjectPicker />
    </>
  );
}

function mount() {
  window.history.replaceState({}, "", "/read/doc-one");
  render(<BrowserRouter><RouteAndKeys /></BrowserRouter>);
}

async function keys(...specs: string[]) {
  await act(async () => {
    for (const spec of specs) press(window, spec, "mac");
  });
}

async function chooseProject(title: string) {
  await keys("ctrl+b", "shift+p");
  const row = await screen.findByRole("button", { name: new RegExp(title) });
  fireEvent.click(row);
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
}

async function expectRefs(refs: string[]) {
  await waitFor(() => {
    const tree = tabs().trees.reading;
    expect(tree).not.toBeNull();
    expect(tree?.root_order.map((id) => tree.nodes[id].ref)).toEqual(refs);
    expect(document.querySelectorAll("[data-document-strip] [data-tab-id]")).toHaveLength(refs.length);
    expect(document.querySelector("[data-document-strip]")?.textContent).not.toContain("Opening your tabs");
  });
}

async function expectActive(ref: string) {
  await waitFor(() => {
    expect(screen.getByTestId("route").textContent).toBe(`/read/${ref}`);
    const tree = tabs().trees.reading;
    expect(tree?.active_tab_id && tree.nodes[tree.active_tab_id].ref).toBe(ref);
    expect(document.querySelector('[data-tab-id][aria-selected="true"]')?.getAttribute("data-tab-id"))
      .toBe(tree?.active_tab_id);
  });
}

beforeEach(() => {
  pinPlatform("mac");
  tabs().resetTabTrees();
  tabs().selectProject(TAB_PROJECT_ID);
  vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
    if (String(input).endsWith("/projects")) {
      return Response.json({ projects: ["Alpha", "Beta"].map((title) => ({
        project_id: title.toLowerCase(), title, kind: "project", member_count: 0,
        order: 0, pinned: false, archived_at: null, primary_document_id: null,
        created_at: "2026-10-04T00:00:00Z", updated_at: null,
      })) });
    }
    return Response.json({}, { status: 404 });
  });
});

afterEach(() => {
  cleanup();
  prefixState.disarm();
  tabs().resetTabTrees();
  tabs().selectProject(TAB_PROJECT_ID);
  clearTabProject();
  unpinPlatform();
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

describe("document tabs follow project context AND route changes", () => {
  it.each([["Alpha", "Beta"], ["Beta", "Alpha"]])(
    "%s → %s → original restores its tabs and previous/next navigation",
    async (original, other) => {
      tabs().selectProject(original.toLowerCase());
      mount();
      await expectRefs(["doc-one"]);
      fireEvent.click(screen.getByRole("link", { name: "Second document" }));
      await expectActive("doc-two");
      await expectRefs(["doc-one", "doc-two"]);

      await chooseProject(other);
      expect(tabs().projectId).toBe(other.toLowerCase());
      // The route did not change. Only this project's current document is
      // adopted, not the previous project's complete tab list.
      await expectRefs(["doc-two"]);
      await expectActive("doc-two");
      await chooseProject(original);
      expect(tabs().projectId).toBe(original.toLowerCase());
      await expectRefs(["doc-one", "doc-two"]);
      await expectActive("doc-two");
      await keys("ctrl+b", "p");
      await expectActive("doc-one");
      await keys("ctrl+alt+]");
      await expectActive("doc-two");
    },
  );

  it("an adapter context replacement reloads the current route without a navigation", async () => {
    mount();
    await expectRefs(["doc-one"]);
    fireEvent.click(screen.getByRole("link", { name: "Second document" }));
    await expectRefs(["doc-one", "doc-two"]);
    act(() => tabs().setTabTreeAdapter(createInMemoryTabTreeAdapter()));
    await expectRefs(["doc-two"]);
    await expectActive("doc-two");
  });

  it("Cmd+E keeps the tabs and an ordinary same-mothership route change still adopts its document", async () => {
    mount();
    await expectRefs(["doc-one"]);
    fireEvent.click(screen.getByRole("link", { name: "Second document" }));
    await expectActive("doc-two");
    const epoch = tabs().contextEpoch;
    await keys("meta+e");
    expect(screen.getByTestId("route").textContent).toBe("/library");
    await expectRefs(["doc-one", "doc-two"]);
    fireEvent.click(screen.getByRole("link", { name: "Third document" }));
    await expectActive("doc-three");
    await expectRefs(["doc-one", "doc-two", "doc-three"]);
    expect(tabs().contextEpoch).toBe(epoch);
    await keys("ctrl+b", "p");
    await expectActive("doc-two");
  });
});
