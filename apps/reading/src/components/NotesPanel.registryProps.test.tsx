/**
 * NotesPanel.registryProps.test.tsx — a "Notes" panel opened through the
 * generic panel registry with no props (PanelLayoutPanel passes the
 * descriptor's props through, and `ws.open("Notes", {})` is legal) must
 * render its empty feed, not throw on `events.length`.
 *
 * Found in lane A stage B3: cockpitRepairR1's "docked: Esc on body restores
 * both panes" opens a bare Notes panel as the dock to hide; when the lazy
 * chunk resolved inside the test's flush (under full-suite load) the panel
 * threw "Cannot read properties of undefined (reading 'length')" and the
 * test failed intermittently (2 of 3 full runs during this stage).
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" })),
}));

import NotesPanel from "./NotesPanel";

beforeAll(() => {
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
});

afterEach(() => cleanup());

describe("NotesPanel opened with the registry's bare props", () => {
  it("renders an empty feed instead of throwing", () => {
    const Bare = NotesPanel as unknown as (p: Record<string, never>) => JSX.Element;
    expect(() => render(<Bare />)).not.toThrow();
  });
});
