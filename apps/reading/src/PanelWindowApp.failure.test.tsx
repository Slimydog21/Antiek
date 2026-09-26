/**
 * FFX SPR-03 (A-15): /_panel/<id> with no main window to hand off from.
 * The popout handshake (workspace/popout.ts receivePopoutPanel) resolves
 * null after 2 s; PanelWindowApp adds a 10 s backstop for a handshake that
 * never settles. Either way the window ends on "This panel couldn't be
 * opened." with a Close action, and never on transport jargon.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const receivePopoutPanel = vi.hoisted(() => vi.fn());
vi.mock("./workspace/popout", () => ({
  receivePopoutPanel,
  farewellPopout: vi.fn(),
}));
vi.mock("./workspace/WorkspaceStore", () => ({
  disablePersistence: vi.fn(),
  enablePersistence: vi.fn(),
}));
vi.mock("./workspace/PanelRegistry", () => ({ PanelRegistry: {} }));
vi.mock("./components/lemon/LemonToast", () => ({ LemonToastViewport: () => null }));

import PanelWindowApp from "./PanelWindowApp";

function renderAt(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/_panel/${id}`]}>
      <Routes>
        <Route path="/_panel/:panelId" element={<PanelWindowApp />} />
      </Routes>
    </MemoryRouter>,
  );
}

function expectNoJargon(text: string) {
  expect(text).not.toMatch(/BroadcastChannel/);
  expect(text).not.toMatch(/panel id/i);
  expect(text).not.toContain("does-not-exist");
}

beforeEach(() => {
  receivePopoutPanel.mockReset();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("PanelWindowApp — a hand-off that never completes", () => {
  it("a handshake that never settles ends at 10 s on 'This panel couldn't be opened.'", async () => {
    vi.useFakeTimers();
    receivePopoutPanel.mockReturnValue(new Promise(() => {}));
    renderAt("does-not-exist");
    await act(async () => {
      vi.advanceTimersByTime(9_999);
    });
    expect(screen.queryByText("This panel couldn't be opened.")).toBeNull();
    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.getByText("This panel couldn't be opened.")).toBeTruthy();
    expectNoJargon(document.body.textContent ?? "");
  });

  it("a handshake that resolves with nothing shows the failure and a working Close", async () => {
    receivePopoutPanel.mockResolvedValue(null);
    const close = vi.spyOn(window, "close").mockImplementation(() => undefined);
    renderAt("does-not-exist");
    expect(await screen.findByText("This panel couldn't be opened.")).toBeTruthy();
    expectNoJargon(document.body.textContent ?? "");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(close).toHaveBeenCalledTimes(1);
    close.mockRestore();
  });

  it("a handshake that throws does not leave the window spinning", async () => {
    receivePopoutPanel.mockRejectedValue(new Error("BroadcastChannel constructor blocked"));
    renderAt("does-not-exist");
    expect(await screen.findByText("This panel couldn't be opened.")).toBeTruthy();
    expectNoJargon(document.body.textContent ?? "");
  });
});
