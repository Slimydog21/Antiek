/**
 * AppShell.palette.test.tsx — MS-01 F1.
 *
 * Grounding on main 15e78e276 found that ⌘K with focus on the page body did
 * not open the command palette: the shell's keymap dispatched the palette
 * toggle event AND the palette's own window keydown handler toggled it too,
 * so the two flips cancelled out. The NavRail Search button and ⌘⇧P worked
 * because only one path reached them.
 *
 * This mounts the real AppShell (the real keymap dispatcher) with the real
 * CommandPalette beside the routes, exactly as App.tsx composes them, and
 * presses ⌘K from document.body. Heavy chrome that has its own suites is
 * stubbed; nothing on the key path is.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
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

vi.mock("./lib/api", async (orig) => ({
  ...(await orig<typeof import("./lib/api")>()),
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}) })),
}));
vi.mock("./scene/Scene", () => ({ Scene: () => null }));
vi.mock("./shell/MascotStation", () => ({ MascotStation: () => null }));
vi.mock("./shell/NavRail", () => ({ NavRail: () => null }));
vi.mock("./components/ad/AdBorderMount", () => ({ AdBorderMount: () => null }));
vi.mock("./components/windows/WindowsLayer", () => ({ WindowsLayer: () => null }));
vi.mock("./shell/SceneChrome", () => ({
  SceneChrome: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("./components/navigation/Topbar", () => ({ Topbar: () => null }));
vi.mock("./workspace/PanelLayout", () => ({
  PanelLayout: ({ mainSlot }: { mainSlot: React.ReactNode }) => <div>{mainSlot}</div>,
}));
vi.mock("./workspace/useWorkspaceHydration", () => ({
  useWorkspaceHydration: () => {},
}));

import { AppShell } from "./AppShell";
import CommandPalette from "./components/CommandPalette";
import { useWorkspace } from "./workspace/WorkspaceStore";

afterEach(() => {
  cleanup();
  useWorkspace.getState().reset();
  window.localStorage.clear();
});

function mountShellWithPalette() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <AppShell>
        <CommandPalette />
        <div data-testid="route-view">ROUTE</div>
      </AppShell>
    </MemoryRouter>,
  );
}

function pressFromBody(init: KeyboardEventInit) {
  const event = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init });
  act(() => {
    document.body.dispatchEvent(event);
  });
  return event;
}

const palette = () => document.querySelector('[aria-label="Command palette"]');

describe("F1 — ⌘K opens the palette from the page body (one toggle owner)", () => {
  it("⌘K with focus on document.body opens the palette", () => {
    mountShellWithPalette();
    expect(document.activeElement).toBe(document.body);
    expect(palette()).toBeNull();

    pressFromBody({ key: "k", metaKey: true });

    expect(palette(), "⌘K from the body must leave the palette OPEN").toBeTruthy();
  });

  it("⌘⇧P, the palette's second key, still opens it", () => {
    mountShellWithPalette();
    pressFromBody({ key: "P", metaKey: true, shiftKey: true });
    expect(palette()).toBeTruthy();
  });
});
