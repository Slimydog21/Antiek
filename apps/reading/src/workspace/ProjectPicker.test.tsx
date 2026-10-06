/**
 * ProjectPicker.test.tsx — the D2 project level: account-project selection
 * exists in the shortcut table AND in the UI (the D2.1 defect: it was in
 * neither), and a selection RE-FILES the tab trees under it.
 *
 * The key tests press prefix+shift+p / ctrl+alt+p through the REAL
 * dispatcher; on the unfixed code no row answered to those keys, so the
 * dialog never opened. The store tests prove the selection is not cosmetic:
 * trees saved under one project are not another project's.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";

import { installShortcuts } from "./shortcuts";
import { ProjectPicker } from "./ProjectPicker";
import { press } from "./keymapTestKit";
import { clearTabProject, readTabProject } from "./persistence";
import { TAB_PROJECT_ID, useTabTrees } from "./tabTreeStore";

const tabs = () => useTabTrees.getState();
const dialog = () => document.body.querySelector('[role="dialog"]');

const PROJECTS = {
  projects: [
    {
      project_id: "fld-varda",
      title: "Varda diligence",
      kind: "project",
      order: 1,
      pinned: false,
      archived_at: null,
      primary_document_id: null,
      created_at: "2026-09-01T00:00:00Z",
      updated_at: null,
      member_count: 3,
    },
  ],
};

function respond(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response);
}

function stubProjects(status = 200) {
  vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/projects")) return respond(PROJECTS, status);
    return respond({}, 404);
  });
}

async function pressKeys(...specs: string[]) {
  await act(async () => {
    for (const spec of specs) press(window, spec, "mac");
  });
}

/** The store back to the default project, its persistence gone. */
function resetProject() {
  tabs().resetTabTrees();
  tabs().selectProject(TAB_PROJECT_ID);
  clearTabProject();
}

describe("tabTreeStore.selectProject — the selection re-files the trees", () => {
  beforeEach(resetProject);
  afterEach(resetProject);

  it("starts at the default project and persists a switch, clearing it on return", () => {
    expect(tabs().projectId).toBe(TAB_PROJECT_ID);
    expect(readTabProject()).toBeNull();
    tabs().selectProject("fld-a");
    expect(tabs().projectId).toBe("fld-a");
    expect(readTabProject()).toBe("fld-a");
    tabs().selectProject(TAB_PROJECT_ID);
    expect(tabs().projectId).toBe(TAB_PROJECT_ID);
    expect(readTabProject()).toBeNull();
  });

  it("re-selecting the current project is a no-op (no context swap)", () => {
    const epoch = tabs().contextEpoch;
    tabs().selectProject(tabs().projectId);
    expect(tabs().contextEpoch).toBe(epoch);
  });

  it("each project's tabs are its own: a tree saved under one is not the other's", async () => {
    // Open a tab under the default project and let the save land.
    const spawned = tabs().spawnTab("reading", null, {
      tab_id: "root:reader:doc-proj-1",
      kind: "reader",
      ref: "doc-proj-1",
      mothership: "reading",
      activate: true,
    });
    expect(spawned.ok).toBe(true);
    // Flush the queued save (the in-memory adapter resolves at once).
    await act(async () => {});
    await act(async () => {});

    tabs().selectProject("fld-b");
    expect(tabs().trees.reading).toBeNull();
    expect(tabs().loaded.reading).toBe(false);
    await tabs().ensureMothership("reading");
    expect(tabs().trees.reading?.root_order ?? []).toEqual([]);

    tabs().selectProject(TAB_PROJECT_ID);
    await tabs().ensureMothership("reading");
    expect(tabs().trees.reading?.root_order).toEqual(["root:reader:doc-proj-1"]);
  });

  it("a switch mid-load does not file the old project's tree under the new one", async () => {
    const loading = tabs().ensureMothership("reading");
    tabs().selectProject("fld-c");
    await loading;
    // The epoch moved; the in-flight load under the old project was dropped.
    expect(tabs().loaded.reading).toBe(false);
    await tabs().ensureMothership("reading");
    expect(tabs().trees.reading?.root_order ?? []).toEqual([]);
  });
});

describe("the account-project picker (prefix+shift+p)", () => {
  let uninstall: () => void;

  beforeEach(() => {
    resetProject();
    uninstall = installShortcuts(vi.fn() as never);
  });

  afterEach(() => {
    uninstall();
    cleanup();
    vi.unstubAllGlobals();
    resetProject();
    document.body.innerHTML = "";
  });

  it("prefix+shift+p opens the picker: the project level is IN the table", async () => {
    stubProjects();
    render(<ProjectPicker />);
    expect(dialog()).toBeNull();
    await pressKeys("ctrl+b", "shift+p");
    await waitFor(() => expect(dialog()).toBeTruthy());
    await waitFor(() => expect(dialog()!.textContent).toContain("Varda diligence"));
    expect(dialog()!.textContent).toContain("Default project");
  });

  it("ctrl+alt+p, the chord twin, opens the same picker", async () => {
    stubProjects();
    render(<ProjectPicker />);
    await pressKeys("ctrl+alt+p");
    await waitFor(() => expect(dialog()).toBeTruthy());
  });

  it("picking a registry project selects it: store, persistence, dialog close", async () => {
    stubProjects();
    render(<ProjectPicker />);
    await pressKeys("ctrl+b", "shift+p");
    await waitFor(() => expect(dialog()?.textContent).toContain("Varda diligence"));
    // The default project is marked current before the pick.
    const currentBefore = dialog()!.querySelector('[aria-current="true"]');
    expect(currentBefore?.textContent).toContain("Default project");
    const row = Array.from(dialog()!.querySelectorAll<HTMLElement>("button")).find((b) =>
      b.textContent?.includes("Varda diligence"),
    )!;
    await act(async () => {
      fireEvent.click(row);
    });
    await waitFor(() => expect(dialog()).toBeNull());
    expect(tabs().projectId).toBe("fld-varda");
    expect(readTabProject()).toBe("fld-varda");
  });

  it("a registry failure is an honest error with a retry, never a blank dialog", async () => {
    stubProjects(500);
    render(<ProjectPicker />);
    await pressKeys("ctrl+b", "shift+p");
    await waitFor(() => expect(dialog()?.textContent).toContain("Couldn't open your projects"));
    stubProjects(200);
    const retry = Array.from(dialog()!.querySelectorAll<HTMLElement>("button")).find((b) =>
      b.textContent?.includes("Try again"),
    )!;
    await act(async () => {
      fireEvent.click(retry);
    });
    await waitFor(() => expect(dialog()?.textContent).toContain("Varda diligence"));
  });
});
