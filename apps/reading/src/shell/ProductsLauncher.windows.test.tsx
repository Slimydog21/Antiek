/**
 * ProductsLauncher.windows.test.tsx — SPR-09 M5 spawn integration.
 *
 * The launcher gains an additive "open in window" (⊞) affordance for
 * window-eligible, built modes (Library, Stats). Navigate stays the default;
 * ⊞ opens a transparent workspace window over the scene instead.
 *
 * Asserts:
 *   - window-eligible built modes show the ⊞ button;
 *   - clicking ⊞ opens a window in windowsStore (not a navigation) + closes
 *     the launcher;
 *   - a non-eligible mode shows NO ⊞ (windows are opt-in, contract-verified).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ProductsLauncher } from "./ProductsLauncher";
import { useWindows } from "../workspace/windowsStore";

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

function renderLauncher(onClose = vi.fn()) {
  render(
    <MemoryRouter>
      <ProductsLauncher open onClose={onClose} />
    </MemoryRouter>,
  );
  return onClose;
}

describe("ProductsLauncher — open in window (M5)", () => {
  it("shows the ⊞ window affordance for the window-eligible Library mode", () => {
    renderLauncher();
    expect(screen.getByLabelText("Open Library in a window")).toBeTruthy();
  });

  it("clicking ⊞ opens a window in the store and closes the launcher (no navigate)", () => {
    const onClose = renderLauncher();
    fireEvent.click(screen.getByLabelText("Open Library in a window"));
    const ws = useWindows.getState();
    expect(ws.order.length).toBe(1);
    expect(ws.windows[ws.order[0]].kind).toBe("library");
    expect(onClose).toHaveBeenCalled();
    // The window path must NOT navigate away — it opens alongside the scene.
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("the Stats run-mode is window-eligible and opens a stats window", () => {
    renderLauncher();
    fireEvent.click(screen.getByLabelText("Open Substrate stats in a window"));
    const ws = useWindows.getState();
    expect(ws.order.length).toBe(1);
    expect(ws.windows[ws.order[0]].kind).toBe("stats");
  });

  it("a non-window-eligible built mode does NOT render a ⊞ button", () => {
    renderLauncher();
    // Sources is a built mode but not contract-verified for windows.
    expect(screen.queryByLabelText("Open Sources in a window")).toBeNull();
  });
});
