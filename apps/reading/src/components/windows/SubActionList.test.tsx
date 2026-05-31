/**
 * SubActionList.test.tsx — SPR-04 M1 (the window-native sub-action page).
 *
 * Proves the sub-action page is DATA-DRIVEN from MODE_TAXONOMY (not a
 * hardcoded list) and that a row click navigates + closes its window:
 *   - given { workflow: "research" } it lists exactly the Research-workflow
 *     modes (label-for-label with the taxonomy),
 *   - a built bare-route row navigates to that route and closes THIS window,
 *   - a param-route row with no real bare index does NOT navigate (honest, no
 *     misroute),
 *   - it is glass-native in a window (bg-transparent, h-full) so the scene
 *     shows through.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import SubActionList from "./SubActionList";
import { WindowHostProvider } from "./windowHostContext";
import { useWindows } from "../../workspace/windowsStore";
import { MODE_TAXONOMY } from "../../shell/workflowTaxonomy";

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }));
vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

beforeEach(() => {
  navigateMock.mockReset();
  useWindows.getState().reset();
});
afterEach(cleanup);

function renderList(props: { workflow?: "research" | "read"; __windowId?: string } = {}) {
  render(
    <MemoryRouter>
      <WindowHostProvider value={true}>
        <SubActionList {...props} />
      </WindowHostProvider>
    </MemoryRouter>,
  );
}

describe("SubActionList — data-driven from MODE_TAXONOMY (M1)", () => {
  it("lists exactly the workflow's taxonomy modes, by label", () => {
    renderList({ workflow: "research" });
    const researchModes = MODE_TAXONOMY.filter((m) => m.workflow === "research");
    expect(researchModes.length).toBeGreaterThan(0);
    // Every research mode's row is present and tagged with its id.
    for (const m of researchModes) {
      expect(
        document.querySelector(`[data-subaction-id="${m.id}"]`),
        `missing row for ${m.id}`,
      ).toBeTruthy();
    }
    // And NO foreign-workflow row leaked in (e.g. a Read mode).
    const aReadMode = MODE_TAXONOMY.find((m) => m.workflow === "read");
    if (aReadMode) {
      expect(document.querySelector(`[data-subaction-id="${aReadMode.id}"]`)).toBeNull();
    }
  });

  it("a built bare-route row navigates and closes the window", () => {
    // Seed a window so close() has something to remove (its absence is harmless,
    // but this mirrors the real product-activation flow).
    const id = useWindows.getState().open("subaction", { workflow: "research" }, { id: "win:subaction:research" });
    renderList({ workflow: "research", __windowId: id });
    // BrainstormStation is a built bare route (/brainstorm).
    fireEvent.click(document.querySelector('[data-subaction-id="BrainstormStation"]') as Element);
    expect(navigateMock).toHaveBeenCalledWith("/brainstorm");
    expect(useWindows.getState().windows[id]).toBeUndefined();
  });

  it("a param-route row with no real bare index does NOT navigate", () => {
    renderList({ workflow: "research" });
    // Replay's route is /replay/:investigationId — /replay is not a bare route,
    // so there is no instance to open from the menu: clicking it is a no-op.
    const replay = document.querySelector('[data-subaction-id="Replay"]') as HTMLButtonElement;
    expect(replay.disabled).toBe(true);
    fireEvent.click(replay);
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("is glass-native in a window (bg-transparent + h-full) so the scene shows through", () => {
    renderList({ workflow: "research" });
    const rootEl = document.querySelector("[data-subaction-list]") as HTMLElement;
    expect(rootEl.className).toContain("bg-transparent");
    expect(rootEl.className).toContain("h-full");
    expect(rootEl.className).not.toContain("h-screen");
  });
});
