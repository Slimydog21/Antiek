/**
 * projectTree.project.test.tsx — the sidebar's project row: account-project
 * selection in the UI, not only behind a key (the D2.1 defect's other
 * half). The row names the project the tab trees file under and opens the
 * SAME picker the prefix+shift+p key opens.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ProjectTree } from "./ProjectTree";
import { SHORTCUT_EVENTS } from "../workspace/shortcuts";
import { clearTabProject } from "../workspace/persistence";
import { TAB_PROJECT_ID, useTabTrees } from "../workspace/tabTreeStore";

const tabs = () => useTabTrees.getState();

function respond(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response);
}

function resetProject() {
  tabs().resetTabTrees();
  tabs().selectProject(TAB_PROJECT_ID);
  clearTabProject();
}

describe("the sidebar's project row", () => {
  beforeEach(() => {
    resetProject();
    vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/books")) return respond({ books: [], count: 0 });
      if (url.includes("/investigations")) return respond({ count: 0, investigations: [] });
      return respond({}, 404);
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    resetProject();
    document.body.innerHTML = "";
  });

  it("names the project the trees file under, and follows a switch", async () => {
    render(
      <MemoryRouter initialEntries={["/library"]}>
        <ProjectTree />
      </MemoryRouter>,
    );
    const shown = await waitFor(() => {
      const el = document.body.querySelector<HTMLElement>("[data-current-project]");
      expect(el).toBeTruthy();
      return el!;
    });
    expect(shown.textContent).toBe(TAB_PROJECT_ID);
    act(() => tabs().selectProject("fld-sidebar"));
    expect(document.body.querySelector<HTMLElement>("[data-current-project]")!.textContent).toBe(
      "fld-sidebar",
    );
  });

  it("opens the SAME picker as the key (one event, one path)", async () => {
    render(
      <MemoryRouter initialEntries={["/library"]}>
        <ProjectTree />
      </MemoryRouter>,
    );
    const fired = vi.fn();
    window.addEventListener(SHORTCUT_EVENTS.PROJECT_SELECT_TOGGLE, fired);
    const row = await waitFor(() => {
      const el = Array.from(document.body.querySelectorAll<HTMLElement>("button")).find((b) =>
        b.getAttribute("aria-label")?.includes("account project"),
      );
      expect(el).toBeTruthy();
      return el!;
    });
    fireEvent.click(row);
    window.removeEventListener(SHORTCUT_EVENTS.PROJECT_SELECT_TOGGLE, fired);
    expect(fired).toHaveBeenCalledTimes(1);
  });
});
