import { act, cleanup, render, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DocumentTabStrip } from "./DocumentTabStrip";
import { syncRouteToTree } from "./routeSync";
import { createInMemoryTabTreeAdapter, emptyTabTree, toSnapshot } from "./tabTree";
import { setTabOwner } from "./tabTreeOwner";
import { useTabTrees } from "./tabTreeStore";

vi.mock("../lib/api", async (original) => ({
  ...(await original<typeof import("../lib/api")>()),
  apiFetch: vi.fn(async () => new Response("{}", { status: 404 })),
}));
const tabs = () => useTabTrees.getState();
beforeEach(() => { setTabOwner(null); setTabOwner("owner-A"); tabs().resetTabTrees(); window.history.replaceState({}, "", "/read/visible-doc"); });
afterEach(() => { cleanup(); setTabOwner(null); tabs().resetTabTrees(); window.history.replaceState({}, "", "/"); vi.restoreAllMocks(); });

it("the mounted strip reloads the current route after owner invalidation", async () => {
  render(<BrowserRouter><DocumentTabStrip /></BrowserRouter>);
  await waitFor(() => expect(tabs().trees.reading?.active_tab_id).toBeTruthy());
  const oldId = tabs().trees.reading!.active_tab_id;
  act(() => { setTabOwner("owner-B"); });
  await waitFor(() => expect(tabs().trees.reading?.active_tab_id).toBeTruthy());
  const active = tabs().trees.reading!.active_tab_id!;
  expect(active).not.toBe(oldId);
  expect(tabs().trees.reading!.nodes[active].ref).toBe("visible-doc");
});

it("an obsolete async route load cannot adopt its route into a replacement project context", async () => {
  const original = createInMemoryTabTreeAdapter();
  let release: (value: ReturnType<typeof toSnapshot>) => void = () => {};
  const gate = new Promise<ReturnType<typeof toSnapshot>>((done) => { release = done; });
  tabs().setTabTreeAdapter({ ...original, load: () => gate });
  const syncing = syncRouteToTree("reading", "/read/old-private-route");
  tabs().setTabTreeAdapter(createInMemoryTabTreeAdapter());
  await tabs().ensureMothership("reading");
  release(toSnapshot(emptyTabTree("reading"))); await syncing;
  expect(tabs().trees.reading!.nodes).toEqual({});
});
