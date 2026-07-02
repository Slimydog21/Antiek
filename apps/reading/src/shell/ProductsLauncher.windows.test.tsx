/**
 * ProductsLauncher.windows.test.tsx — SPR-09 M5 spawn integration.
 *
 * The launcher exposes an additive "open in window" (⊞) affordance for
 * window-eligible, built modes (Library, Stats, Documents). Navigate stays the
 * default for mode rows; ⊞ opens a transparent workspace window over the scene.
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

const { listDeliverablesMock, navigateMock } = vi.hoisted(() => ({
  listDeliverablesMock: vi.fn(),
  navigateMock: vi.fn(),
}));
vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  listDeliverables: listDeliverablesMock,
}));

beforeEach(() => {
  listDeliverablesMock.mockReset().mockResolvedValue({ count: 0, deliverables: [] });
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

  it("the shared Documents mode is window-eligible and opens a documents window", () => {
    renderLauncher();
    fireEvent.click(screen.getByLabelText("Open Documents in a window"));
    const ws = useWindows.getState();
    expect(ws.order.length).toBe(1);
    expect(ws.windows[ws.order[0]].kind).toBe("documents");
  });

  it("uses the canonical privacy dashboard label in Run & settings", () => {
    const onClose = renderLauncher();

    fireEvent.click(screen.getByRole("button", { name: "Privacy dashboard" }));

    expect(navigateMock).toHaveBeenCalledWith("/privacy");
    expect(onClose).toHaveBeenCalled();
    expect(useWindows.getState().order.length).toBe(0);
    expect(screen.queryByText("Privacy & deletion")).toBeNull();
  });

  it("uses the canonical Trust Center label in Run & settings", () => {
    const onClose = renderLauncher();

    fireEvent.click(screen.getByRole("button", { name: "Trust Center" }));

    expect(navigateMock).toHaveBeenCalledWith("/trust");
    expect(onClose).toHaveBeenCalled();
    expect(useWindows.getState().order.length).toBe(0);
    expect(screen.queryByText("Trust & safety")).toBeNull();
  });

  it("a non-window-eligible built mode does NOT render a ⊞ button", () => {
    renderLauncher();
    // Sources is a built mode but not contract-verified for windows.
    expect(screen.queryByLabelText("Open Sources in a window")).toBeNull();
  });

  it("surfaces live Write pieces and opens them in the Write loop", async () => {
    listDeliverablesMock.mockResolvedValue({
      count: 3,
      deliverables: [
        {
          deliverable_id: " dlv-live ",
          title: "  Live memo  ",
          investigation_root_id: " inv-live ",
          section_count: 2,
        },
        { deliverable_id: "dlv-untitled", title: " ", section_count: 0 },
        { deliverable_id: " ", title: "Skipped memo", section_count: 1 },
      ],
    });
    const onClose = renderLauncher();

    expect(await screen.findByText("Recent writing")).toBeTruthy();
    fireEvent.click(await screen.findByText("Live memo"));

    expect(navigateMock).toHaveBeenCalledWith("/write/dlv-live");
    expect(onClose).toHaveBeenCalled();
    expect(useWindows.getState().order.length).toBe(0);
    expect(screen.queryByText("Skipped memo")).toBeNull();
  });

  it("filters Write pieces with the launcher query and Enter opens the active piece", async () => {
    listDeliverablesMock.mockResolvedValue({
      count: 2,
      deliverables: [
        { deliverable_id: "dlv-alpha", title: "Alpha memo", section_count: 1 },
        { deliverable_id: "dlv-beta", title: "Beta memo", section_count: 0 },
      ],
    });
    const onClose = renderLauncher();

    const input = screen.getByPlaceholderText("Filter…");
    await screen.findByText("Alpha memo");
    fireEvent.change(input, { target: { value: "beta" } });
    expect(screen.queryByText("Alpha memo")).toBeNull();
    expect(screen.getByText("Beta memo")).toBeTruthy();

    fireEvent.keyDown(input, { key: "Enter" });

    expect(navigateMock).toHaveBeenCalledWith("/write/dlv-beta");
    expect(onClose).toHaveBeenCalled();
  });
});
