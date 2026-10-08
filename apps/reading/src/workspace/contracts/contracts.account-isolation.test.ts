/**
 * contracts.account-isolation.test.ts — I19: the selection mirror and the
 * registry cache never carry one account's state into another's session.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";

import { setWorkspaceOwner } from "../../lib/accountWorkspaceOwner";
import { clearTabProject, readTabProject } from "../persistence";
import { TAB_PROJECT_ID, useTabTrees } from "../tabTreeStore";
import { usePreBackendTreeFeed } from "./adapters/preBackend";
import { useSelection } from "./selection";
import { markTreeUnfed, useContextTreeStore } from "./treeStore";

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}
const fetches = vi.fn<typeof fetch>();

beforeEach(() => {
  setWorkspaceOwner("account-a");
  useTabTrees.getState().resetTabTrees();
  clearTabProject();
  useTabTrees.getState().selectProject(TAB_PROJECT_ID);
  markTreeUnfed();
  fetches.mockReset().mockImplementation(async (input) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path.endsWith("/projects")) return response({ projects: [] });
    if (path.endsWith("/investigations")) return response({ count: 0, investigations: [] });
    throw new Error(`Unexpected request: ${path}`);
  });
  vi.stubGlobal("fetch", fetches);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearTabProject();
  setWorkspaceOwner("account-a");
  clearTabProject();
  markTreeUnfed();
  setWorkspaceOwner(null);
});

const projectFetches = () => fetches.mock.calls.filter(([i]) => new URL(String(i), "http://localhost").pathname.endsWith("/projects")).length;

describe("I19 account switch", () => {
  it("re-seeds the selection from the new owner's persistence and refetches the registry", async () => {
    const { unmount } = renderHook(() => usePreBackendTreeFeed({ investigationLimit: 5 }));
    await waitFor(() => expect(projectFetches()).toBe(1));
    await waitFor(() => expect(useContextTreeStore.getState().tree.status).toBe("ready"));
    expect(useSelection.getState().selectProject("p-a")).toBe(true);
    expect(readTabProject()).toBe("p-a");
    expect(useSelection.getState().selection).toEqual({ projectId: "p-a" });

    act(() => { setWorkspaceOwner("account-b"); });
    expect(readTabProject()).toBeNull();
    expect(useSelection.getState().selection).toEqual({ projectId: TAB_PROJECT_ID });
    expect(useTabTrees.getState().projectId).toBe(TAB_PROJECT_ID);
    await waitFor(() => expect(projectFetches()).toBe(2));

    act(() => { setWorkspaceOwner("account-a"); });
    expect(readTabProject()).toBe("p-a");
    expect(useSelection.getState().selection).toEqual({ projectId: "p-a" });
    await waitFor(() => expect(projectFetches()).toBe(3));
    unmount();
    await waitFor(() => expect(useContextTreeStore.getState().tree.status).toBe("unfed"));
  });
});
