import { unitAccountKey } from "../testAccountOwner";
/**
 * CommandPalette.resetLayout.test.tsx — G-X2 (GAPS §8).
 *
 * "Reset workspace layout" doesn't stick: the palette clears the saved layout
 * key, then the workspace store's debounced persistence write (~250 ms later)
 * writes the emptied layout back into the same key. The route variant also
 * cleared the WRONG key — the raw pathname instead of the collapsed route key
 * useWorkspaceHydration writes under (so on /wrestle/doc-1 it cleared
 * "…route./wrestle/doc-1" while the layout lives under "…route./wrestle/:id").
 *
 * These tests mount the real CommandPalette with the real
 * useWorkspaceHydration (it targets the persistence scope) and wait past the
 * 250 ms debounce — the window where the write-back used to land.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

beforeAll(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }
});

import CommandPalette from "./CommandPalette";
import { useWorkspaceHydration } from "../workspace/useWorkspaceHydration";
import { useWorkspace } from "../workspace/WorkspaceStore";

// Mount AppShell's hydration (the scope owner) beside the palette, the way
// App.tsx composes them — minus the chrome this test doesn't need.
function Harness() {
  useWorkspaceHydration();
  return <CommandPalette />;
}

function mountAt(path: string) {
  window.history.replaceState(null, "", path);
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Harness />
    </MemoryRouter>,
  );
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

function lsKeys(): string[] {
  const out: string[] = [];
  for (let i = 0; i < window.localStorage.length; i++) {
    const k = window.localStorage.key(i);
    if (k) out.push(k);
  }
  return out;
}

function runPaletteCommand(title: string) {
  act(() => {
    window.dispatchEvent(new Event("antiek:palette:toggle"));
  });
  const input = document.querySelector<HTMLInputElement>(
    '[aria-label="Command palette"] input',
  )!;
  fireEvent.change(input, { target: { value: title } });
  const first = document.querySelector('[aria-label="Command palette"] ul li');
  expect(first?.textContent ?? "").toContain(title);
  act(() => {
    fireEvent.keyDown(input, { key: "Enter" });
  });
}

beforeEach(() => {
  window.localStorage.clear();
  useWorkspace.getState().reset();
});

afterEach(() => {
  cleanup();
  useWorkspace.getState().reset();
  window.localStorage.clear();
  window.history.replaceState(null, "", "/");
});

describe("G-X2 — a reset stays reset (no debounced write-back)", () => {
  it("'Reset workspace layout (this investigation)' leaves the key cleared after the 250 ms write-back window", async () => {
    mountAt("/inv/abc");
    await act(async () => {});
    act(() => {
      useWorkspace.getState().open("Notes", {}, { mode: "floating", id: "t:notes", title: "Notes" });
    });
    await act(async () => {
      await wait(300);
    });
    expect(lsKeys()).toContain(unitAccountKey("antiek.workspace.inv.abc"));

    runPaletteCommand("Reset workspace layout (this investigation)");
    expect(lsKeys(), "cleared immediately").not.toContain(unitAccountKey("antiek.workspace.inv.abc"));

    // The defect window: the persistence subscriber used to schedule a
    // snapshot of the emptied workspace ~250 ms after reset().
    await act(async () => {
      await wait(300);
    });
    expect(
      lsKeys(),
      "the emptied layout must NOT be written back into the cleared key",
    ).not.toContain(unitAccountKey("antiek.workspace.inv.abc"));
  });

  it("'Reset workspace layout (this route)' clears the collapsed route key on a dynamic route", async () => {
    mountAt("/wrestle/doc-1");
    await act(async () => {});
    act(() => {
      useWorkspace.getState().open("Notes", {}, { mode: "floating", id: "t:notes", title: "Notes" });
    });
    await act(async () => {
      await wait(300);
    });
    expect(
      lsKeys(),
      "hydration persists the route scope under the collapsed key",
    ).toContain(unitAccountKey("antiek.workspace.route./wrestle/:id"));

    runPaletteCommand("Reset workspace layout (this route)");
    await act(async () => {
      await wait(300);
    });

    const keys = lsKeys();
    expect(keys, "the collapsed route key must be cleared (and stay cleared)").not.toContain(
      unitAccountKey("antiek.workspace.route./wrestle/:id"),
    );
    expect(keys, "no raw-pathname variant of the key may linger either").not.toContain(
      unitAccountKey("antiek.workspace.route./wrestle/doc-1"),
    );
  });
});
